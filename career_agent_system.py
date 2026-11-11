#!/usr/bin/env python3
"""CLI entry point. Modes: live-pipeline | daily-news | morning-digest | evening-review | daemon | install-cron | apply | new-agent | scrub-private | serve."""
import argparse, datetime as dt, importlib.abc, importlib.util, json, os, pathlib, subprocess, sys, time

_HERE = pathlib.Path(__file__).resolve().parent


class _DirectFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        rel = fullname.replace(".", "/")
        pkg = _HERE / rel / "__init__.py"
        if pkg.is_file():
            return importlib.util.spec_from_file_location(fullname, pkg, submodule_search_locations=[str(pkg.parent)])
        mod = _HERE / (rel + ".py")
        if mod.is_file():
            return importlib.util.spec_from_file_location(fullname, mod)
        return None


if not any(isinstance(f, _DirectFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _DirectFinder())

from live import VERSION
from live.profile import ROOT, PRIVATE_KEYS, split_private, check_profile
from live.vault import VaultAgent
from live import runtime

DAILY_NEWS_AGENTS = ["scanner", "aiupdates", "youtube", "contests", "matcher", "dailynews"]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def scrub_private(vault, log=print):
    """Move contact details out of the committed Vault profile into git-ignored private/profile.json."""
    prof = vault.load_artifact("user_profile_v1.json") or {}
    pub, priv = split_private(prof)
    if not priv:
        log("Vault profile is already clean.")
        return
    target = ROOT / "private" / "profile.json"
    target.parent.mkdir(exist_ok=True)
    old = json.loads(target.read_text()) if target.exists() else {}
    target.write_text(json.dumps({**priv, **old}, indent=2))
    vault.save_artifact("user_profile_v1.json", pub, "application/json", ["profile"], "SYSTEM")
    log(f"Moved {sorted(priv)} to private/profile.json. NOTE: earlier commits still contain them; see README 'Purging history'.")


def build_resume(vault, job_arg="", out_dir=None, log=print):
    """Offline: render a resume straight from the Vault (no scanning). Optionally tailored to a pasted job description or a .txt file."""
    from live import resume as R
    from live.profile import merged_profile
    p = merged_profile(vault)
    job = None
    if job_arg:
        f = pathlib.Path(job_arg)
        text = f.read_text("utf-8") if len(job_arg) < 255 and f.is_file() else job_arg
        job = {"id": "custom", "title": text.strip().splitlines()[0][:80], "company": "", "desc": text}
    runtime.discover()
    data = R.build(p, job)
    if job:
        data["summary"] = R.llm_summary(p, data, job, runtime.TOOLS["ask_llm"]) or data["summary"]
    out = pathlib.Path(out_dir or ROOT / "private" / "resumes")
    out.mkdir(parents=True, exist_ok=True)
    stem = "custom" if job else "_base"
    info = R.render_pdf(data, out / f"{stem}.pdf")
    (out / f"{stem}.md").write_text(R.render_md(data), "utf-8")
    log(f"Wrote {out / (stem + '.pdf')} ({info['pages']} page, {info['font']}pt{', least relevant items dropped to fit' if info['dropped'] else ''})")
    if job:
        log(f"Job keyword coverage {data['ats']}%; not in your vault (do not claim): {', '.join(data['missing']) or 'none'}")
    return data


def import_profile(vault, path, log=print):
    """Merge a JSON file into the Vault profile through the Vault (keeps the SHA-256 manifest valid). Contact details go to private/profile.json."""
    incoming = json.loads(pathlib.Path(path).read_text("utf-8"))
    problems = check_profile(incoming)
    if problems:
        for x in problems:
            log(f"! {x}")
        raise SystemExit("Fix the problems above and run import-profile again (nothing was saved).")
    pub, priv = split_private(incoming)
    current = vault.load_artifact("user_profile_v1.json") or {}
    vault.save_artifact("user_profile_v1.json", {**current, **pub}, "application/json", ["profile"], "SYSTEM")
    if priv:
        target = ROOT / "private" / "profile.json"
        target.parent.mkdir(exist_ok=True)
        old = json.loads(target.read_text()) if target.exists() else {}
        target.write_text(json.dumps({**old, **priv}, indent=2))
    log(f"Vault updated: {sorted(pub)}" + (f"; private/profile.json updated: {sorted(priv)}" if priv else ""))


def install_cron(log=print):
    """Install or display local OS cron schedule for 06:00 AM, 08:00 AM, and 07:00 PM autonomous execution."""
    py = sys.executable
    script = str((ROOT / "career_agent_system.py").resolve())
    log_file = str((ROOT / "private" / "cron.log").resolve())
    (ROOT / "private").mkdir(parents=True, exist_ok=True)
    lines = [
        f"0 6 * * * cd {ROOT.resolve()} && {py} {script} --mode daily-news >> {log_file} 2>&1",
        f"0 8 * * * cd {ROOT.resolve()} && {py} {script} --mode morning-digest >> {log_file} 2>&1",
        f"0 19 * * * cd {ROOT.resolve()} && {py} {script} --mode evening-review >> {log_file} 2>&1",
    ]
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = [ln for ln in (cur.stdout or "").splitlines() if "career_agent_system.py" not in ln]
        merged = "\n".join(existing + lines).strip() + "\n"
        proc = subprocess.run(["crontab", "-"], input=merged, text=True, capture_output=True)
        if proc.returncode == 0:
            log("Installed local crontab entries (06:00 daily-news, 08:00 morning-digest, 19:00 evening-review):")
            for ln in lines:
                log("  " + ln)
            return True
    except Exception:
        pass
    log("Add these lines to your crontab (`crontab -e`) or run `python3 career_agent_system.py --mode daemon`:")
    for ln in lines:
        log("  " + ln)
    return False


def run_daemon(vault, log=print):
    """Standalone 24/7 Python scheduler loop (zero external AI assistant involvement). Triggers at 06:00, 08:00, and 19:00 IST."""
    from live.env_loader import load_env
    log("Career Agent Autonomous Daemon started (IST schedule: 06:00 daily-news | 08:00 morning-digest | 19:00 evening-review)")
    fired = set()
    while True:
        now = dt.datetime.now(IST)
        key = (now.date().isoformat(), now.strftime("%H:%M"))
        if key not in fired:
            if key[1] == "06:00":
                fired.add(key)
                load_env(ROOT)
                os.environ["DAILY_NEWS_SEND"] = "1"
                os.environ["DIGEST_SEND"] = "0"
                runtime.run_pipeline(vault, log, only_agents=DAILY_NEWS_AGENTS)
            elif key[1] == "08:00":
                fired.add(key)
                load_env(ROOT)
                os.environ["DIGEST_SEND"] = "1"
                runtime.run_pipeline(vault, log)
            elif key[1] == "19:00":
                fired.add(key)
                load_env(ROOT)
                os.environ["EVENING_REVIEW_SEND"] = "1"
                os.environ["DIGEST_SEND"] = "0"
                runtime.run_pipeline(vault, log)
        time.sleep(30)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="career_agent_system", description=f"Career Agent System v{VERSION}")
    ap.add_argument(
        "--mode",
        default="live-pipeline",
        choices=[
            "live-pipeline",
            "morning-digest",
            "daily-news",
            "evening-review",
            "daemon",
            "install-cron",
            "sync-vault",
            "check-sources",
            "check-env",
            "fetch-keys-from-gmail",
            "send-mail",
            "test-mail",
            "apply",
            "new-agent",
            "scrub-private",
            "import-profile",
            "build-resume",
            "serve",
            "user-backend",
        ],
    )
    ap.add_argument("--serve", action="store_true", help="serve mode: start the local HTTP dashboard and API server (alias for --mode serve)")
    ap.add_argument("--port", type=int, default=8000, help="serve mode: local HTTP port (default 8000)")
    ap.add_argument("--check-env", action="store_true", help="inspect .env/ folder secret keys and which agents use them")
    ap.add_argument("--set-key", action="append", default=[], metavar="KEY=VALUE", help="save a secret key into .env/secrets.env and .env/keys.json")
    ap.add_argument("--auto-tag", default="", help="optional git tag")
    ap.add_argument("--submit", action="store_true", help="apply mode: really submit (asks y/n per job)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if no postings were fetched or a source failed (for CI)")
    ap.add_argument("--dry-run", action="store_true", help="send-mail: build and audit but do not send")
    ap.add_argument("--file", default="", help="import-profile: JSON file with your profile, projects, experience ...")
    ap.add_argument("--job", default="", help="build-resume: paste a job description (or a path to a .txt file) to tailor the resume to; omit for the base resume")
    ap.add_argument("--desc", default="", help="new-agent: what the plugin should do")
    ap.add_argument("--vault", default=str(ROOT / "vault"))
    a = ap.parse_args(argv)
    if getattr(a, "serve", False):
        a.mode = "serve"
    from live.env_loader import load_env, set_secret, env_status
    load_env()
    if a.set_key:
        for item in a.set_key:
            if "=" not in item:
                sys.exit(f"--set-key expects KEY=VALUE, got: {item!r}")
            k, v = item.split("=", 1)
            written = set_secret(k, v)
            print(f"Saved {sorted(written.keys())} into .env/secrets.env and .env/keys.json (chmod 600)")
        if not a.check_env and a.mode == "live-pipeline" and len(sys.argv if argv is None else argv) <= 2 * len(a.set_key) + 1:
            a.check_env = True
    if a.mode == "fetch-keys-from-gmail":
        from live.env_loader import fetch_keys_from_gmail
        fetch_keys_from_gmail(ROOT, print)
        a.check_env = True
    if a.check_env or a.mode == "check-env":
        st = env_status()
        print(f"=== .ENV FOLDER SECRET VAULT: {st['env_folder']} ===")
        print(f"Files in .env/: {', '.join(st['files'])}")
        print(f"{'KEY':<26} {'STATUS':<10} {'VALUE (MASKED)':<28} {'USED BY AGENTS'}")
        print("-" * 92)
        for r in st["keys"]:
            print(f"{r['key']:<26} {r['status']:<10} {r['masked']:<28} {', '.join(r['agents'])}")
        return
    vault = VaultAgent(vault_dir=a.vault)
    vault.bootstrap_defaults_if_empty()
    if a.mode == "install-cron":
        install_cron(print)
        return
    if a.mode == "daemon":
        run_daemon(vault, print)
        return
    if a.mode == "daily-news":
        os.environ["DAILY_NEWS_SEND"] = "1"
        os.environ["DIGEST_SEND"] = "0"
        ctx = runtime.run_pipeline(vault, print, only_agents=DAILY_NEWS_AGENTS)
        print(f"Daily News completed: {len(ctx.get('insights', {}).get('ai_updates', []))} AI news, {len(ctx.get('matches', []))} matched jobs.")
        return
    if a.mode == "evening-review":
        os.environ["EVENING_REVIEW_SEND"] = "1"
        os.environ["DIGEST_SEND"] = "0"
        a.mode = "live-pipeline"
    elif a.mode in ("morning-digest", "sync-vault"):
        os.environ["DIGEST_SEND"] = "1" if a.mode == "morning-digest" else "0"
        a.mode = "live-pipeline"
    if a.mode in ("live-pipeline", "check-sources"):
        if a.mode == "live-pipeline":
            ctx = runtime.run_pipeline(vault, print)
        else:
            from live.profile import merged_profile
            runtime.discover()
            ctx = {"vault": vault, "profile": merged_profile(vault), "log": print, "insights": {}}
            runtime.AGENTS["scanner"]().run(ctx)
        health = ctx.get("insights", {}).get("source_health", [])
        if a.mode == "check-sources" or a.strict or any(h.get("count") for h in health):
            for h in health:
                print(f"{'OK ' if h['count'] and not h['error'] else 'BAD'} {h['source']:<40} {h['count']:>4}  {h.get('ms', 0):>6} ms  {h['error'] or ''}")
        print(f"total unique postings: {len(ctx.get('jobs', []))}")
        if a.mode == "live-pipeline":
            matches = ctx.get("matches", [])
            print(f"\n=== TOP MATCHED JOBS ({len(matches)} matches >= threshold) ===")
            for idx, m in enumerate(matches[:15], 1):
                pay_s = f" | {m['pay']}" if m.get("pay") else ""
                print(f"  {idx:>2}. [{m['score']:>2}% Match | ATS {str(m.get('ats') or '-')+'%':>4}] {m['title']} @ {m['company']} ({m['location']}{pay_s})")
                print(f"      URL: {m['url']}")
                print(f"      Matched Skills: {', '.join(m.get('skills', [])[:8]) or 'none'} | To Learn: {', '.join(m.get('missing', [])[:5]) or 'none'}")
            contests = ctx.get("insights", {}).get("contests", [])
            if contests:
                print(f"\n=== ACTIVE INDIA HACKATHONS & HIRING CHALLENGES ({len(contests)} live) ===")
                for idx, c in enumerate(contests[:8], 1):
                    print(f"  {idx:>2}. [{c.get('type')}] {c['title']} — {c.get('reward')}")
                    print(f"      URL: {c['url']}")
            certs = ctx.get("insights", {}).get("certs", [])
            print(f"\n=== RANKED FREE CERTIFICATIONS & COURSES ({len(certs)} verified) ===")
            for idx, c in enumerate(certs[:12], 1):
                print(f"  {idx:>2}. {c['name']} ({c['provider']} — {c['free_claim']})")
                print(f"      Covers Skills: {', '.join(c.get('covers', []))} | URL: {c['url']}")
            gaps = ctx.get("insights", {}).get("skill_gaps", [])
            if gaps:
                print("\n=== IN-DEMAND SKILL GAPS ACROSS SCANNED JOBS ===")
                print("  " + ", ".join(f"{g['skill']} ({g['jobs']}/{g['of']} jobs)" for g in gaps))
        if a.strict and (not ctx.get("jobs") or any(h["error"] for h in health)):
            sys.exit(1)
    elif a.mode == "send-mail":
        from live.outbox import send_drafts
        send_drafts(vault, print, dry_run=a.dry_run)
    elif a.mode == "test-mail":
        from live.outbox import test_mail
        sys.exit(0 if test_mail(vault, print) else 1)
    elif a.mode == "apply":
        from live.applier import apply_jobs
        apply_jobs(vault, print, submit=a.submit)
    elif a.mode == "new-agent":
        if not a.desc:
            sys.exit("--desc is required")
        runtime.discover()
        from live.builder import new_agent
        new_agent(a.desc)
    elif a.mode == "import-profile":
        if not a.file:
            sys.exit("--file is required")
        import_profile(vault, a.file)
    elif a.mode == "build-resume":
        build_resume(vault, a.job)
    elif a.mode == "scrub-private":
        scrub_private(vault)
    elif a.mode == "serve":
        from live.server import serve
        serve(vault, port=a.port, log=print)
    elif a.mode == "user-backend":
        from live.user_data_backend import serve_user_backend
        serve_user_backend(port=a.port, log=print)



if __name__ == "__main__":
    main()
