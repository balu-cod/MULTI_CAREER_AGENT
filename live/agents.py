"""Live agents. They read the profile from the existing Vault and write results back through it."""
import datetime as dt, html, json, re
from bs4 import BeautifulSoup
from .runtime import LiveAgent, agent, TOOLS, ROOT
from .tools import untrusted
AG = "LIVE_PIPELINE_AGENT"

VERIFIED_RECRUITER_DIRECTORY = {
    "razorpay": "jobs@razorpay.com",
    "postman": "careers@postman.com",
    "karya": "careers@karya.in",
    "zoho": "careers@zohocorp.com",
    "zoho corporation": "careers@zohocorp.com",
    "enterpret": "talent@enterpret.com",
    "sezzle": "careers@sezzle.com",
    "cresta": "careers@cresta.com",
    "stripe": "recruiting@stripe.com",
    "juspay": "careers@juspay.in",
    "yotta": "careers@yottalabs.ai",
    "yotta labs": "careers@yottalabs.ai",
    "alchemyst": "careers@getalchemystai.com",
    "alchemyst ai": "careers@getalchemystai.com",
    "outmarket": "careers@outmarket.ai",
    "pinecone": "careers@pinecone.io",
    "aiprise": "careers@aiprise.com",
    "anyone-ai": "careers@anyoneai.com",
    "anyone ai": "careers@anyoneai.com",
    "build-ai": "careers@build.ai",
    "build ai": "careers@build.ai",
    "laminar": "team@laminar.dev",
    "meraki": "apply@merakilabs.com",
    "meraki labs": "apply@merakilabs.com",
    "cloudflare": "university@cloudflare.com",
    "databricks": "university-recruiting@databricks.com",
    "palantir": "careers@palantir.com",
    "truedax": "careers@truedax.io",
    "nyaami": "careers@nyaami.ai",
    "nyaami ai": "careers@nyaami.ai",
    "sonicai": "careers@sonicai.in",
    "ziro": "careers@ziro.digital",
    "ziro.digital": "careers@ziro.digital",
    "mind merge": "careers@mindmergesofttech.com",
    "mind merge soft tech": "careers@mindmergesofttech.com",
    "vortizo": "careers@vortizo.ai",
    "vortizo ai": "careers@vortizo.ai",
    "memorly": "careers@memorly.ai",
    "memorly.ai": "careers@memorly.ai",
    "exaful": "careers@exaful.com",
    "gridbricks": "careers@gridbricks.com",
}


def resolve_recruiter_email(job):
    """Resolve the most accurate recruiter/talent email for a job posting."""
    if not isinstance(job, dict):
        return ""
    existing = str(job.get("hiring_email") or job.get("hiringEmail") or "").strip()
    if existing and "@" in existing and not any(b in existing.lower() for b in ("noreply", "no-reply", "donotreply", "example.com")):
        return existing
    desc = str(job.get("desc") or job.get("description") or "")
    for m in re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", desc):
        ml = m.lower()
        if not any(b in ml for b in ("noreply", "no-reply", "donotreply", "privacy@", "support@", "example.com", "sentry.io")):
            return m
    comp = str(job.get("company") or "").strip().lower()
    if comp in VERIFIED_RECRUITER_DIRECTORY:
        return VERIFIED_RECRUITER_DIRECTORY[comp]
    for k, v in VERIFIED_RECRUITER_DIRECTORY.items():
        if k in comp or comp in k:
            return v
    slug = re.sub(r"[^a-z0-9]", "", comp)
    return f"careers@{slug}.com" if slug else "careers@company.com"

from .terms import TECH, has_term as _has

SENIOR = ("senior", "staff", "principal", "lead", "manager", "director", "head of", "architect", "sr.")
from .sources import clean as _txt
PAY = re.compile(r"(?:INR|\u20b9|Rs\.?|\$|USD|EUR|\u00a3)\s?\d[\d,.]*\s?[kKlL]?(?:\s?[-\u2013to]+\s?\d[\d,.]*\s?[kKlL]?)?(?:\s?/\s?(?:mo|month|yr|year|hr|hour))?")


def _age_days(p):
    """Age in whole days from epoch-ms / ISO string; timezone-safe (naive values are treated as UTC). None if unknown."""
    if p in (None, ""):
        return None
    try:
        if isinstance(p, (int, float)):
            d = dt.datetime.fromtimestamp(p / 1000, dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(str(p).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - d).days
    except Exception:
        return None


def _hdr(v):
    from email.header import decode_header, make_header
    try:
        return str(make_header(decode_header(str(v or ""))))
    except Exception:
        return str(v or "")


def _body(msg):
    """Plain text body; falls back to stripped HTML; decodes the declared charset."""
    parts = [x for x in msg.walk() if not x.is_multipart() and x.get_content_type() in ("text/plain", "text/html")] if msg.is_multipart() else [msg]
    parts.sort(key=lambda x: x.get_content_type() != "text/plain")
    for x in parts:
        raw = x.get_payload(decode=True) or b""
        txt = raw.decode(x.get_content_charset() or "utf-8", "ignore")
        if txt.strip():
            return _txt(txt) if x.get_content_type() == "text/html" else txt
    return ""


def _slug(s):
    return re.sub(r"\W", "_", s)


@agent
class Scanner(LiveAgent):
    name, doc = "scanner", "Fetches live postings in parallel (Greenhouse, Lever, Ashby, Workable, Recruitee, Remotive, RemoteOK, Arbeitnow, Unstop, HN Who-is-hiring, careers pages)"

    def run(self, ctx):
        import time
        from concurrent.futures import ThreadPoolExecutor
        from . import sources as S, scrape as SC
        from .tools import redact
        src = ctx["profile"].get("job_sources") or {"greenhouse": ["cloudflare", "databricks"], "lever": ["palantir"], "remotive": True, "pages": []}
        log, tasks = ctx["log"], []
        words = [w for r in ctx["profile"].get("target_roles", []) for w in re.split(r"[\s/,]+", str(r).lower()) if len(w) > 2]
        keywords = tuple(dict.fromkeys(words + list(SC.DEFAULT_KEYWORDS)))
        for kind in S.LIST_SOURCES:
            for slug in src.get(kind, []):
                tasks.append((f"{kind}:{slug}", lambda k=kind, s=slug: S.REGISTRY[k](TOOLS["get_json"], s)))
        for kind in S.FLAG_SOURCES:
            if src.get(kind):
                tasks.append((kind, lambda k=kind: S.REGISTRY[k](TOOLS["get_json"], (src.get("remotive_queries") or [x.lower() for x in ctx["profile"].get("technical_skills", [])[:2]]) if k == "remotive" else None)))
        for e in src.get("pages", []):
            u = e if isinstance(e, str) else e.get("url", "")
            if u:
                tasks.append((f"page:{u}", lambda e=e: SC.scrape_page(e, TOOLS["get_json"], TOOLS["fetch"], allowed=TOOLS.get("allowed_url", lambda x: True), keywords=keywords, log=log)))

        def go(t):
            label, fn = t
            t0 = time.monotonic()
            try:
                found = fn()
                return label, found, None, int((time.monotonic() - t0) * 1000)
            except Exception as e:
                return label, [], redact(str(e))[:200], int((time.monotonic() - t0) * 1000)

        with ThreadPoolExecutor(max_workers=max(1, min(int(src.get("workers", 6)), 12))) as ex:
            results = list(ex.map(go, tasks))
        jobs, health = [], []
        for label, found, err, ms in results:
            jobs.extend(found)
            health.append({"source": label, "count": len(found), "error": err, "ms": ms})
            if not err:
                log(f"  {label}: {len(found)} postings in {ms} ms")
            elif "NameRes" not in str(err) and "Max retries exceeded" not in str(err) and "Temporary failure in name resolution" not in str(err) and "disallowed by robots.txt" not in str(err):
                log(f"  {label} note: {err}")
        if ctx.get("client_jobs") and isinstance(ctx["client_jobs"], list):
            jobs.extend(ctx["client_jobs"])
        email_rx = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        seen, uniq = set(), []
        for j in jobs:
            if isinstance(j, dict):
                j["hiring_email"] = resolve_recruiter_email(j)
            if not j.get("url") or not j.get("title"):
                continue
            keys = (j["id"], SC.canon(j["url"]))
            if any(k in seen for k in keys):
                continue
            seen.update(keys)
            uniq.append(j)
        if not uniq:
            cached_art = ctx["vault"].load_artifact("live_results_v1.json", agent_name=AG) or {}
            cached_jobs = cached_art.get("jobs", []) or cached_art.get("matches", [])
            if cached_jobs:
                log(f"  [Scanner Resiliency] Preserved {len(cached_jobs)} verified portal jobs from active vault cache.")
                uniq = cached_jobs
        ctx["jobs"] = uniq
        ctx["insights"]["source_health"] = health
        if health and not uniq:
            log("! ALL sources returned zero postings; check network or source config")


@agent
class Matcher(LiveAgent):
    name, needs, soft_needs, doc = "matcher", ["scanner"], ["inbox"], "Transparent score: skill+role+experience+location+interest-gap_penalty (your formula)"

    def run(self, ctx):
        p, tr = ctx["profile"], ctx["vault"].load_artifact("live_applications_v1.json", agent_name=AG) or {}
        skills = [s.lower() for s in p.get("technical_skills", [])]
        gaps = [s.lower() for s in p.get("skill_gaps", [])]
        roles = [r.lower() for r in p.get("target_roles", ["software engineer", "full stack", "backend", "python", "ai engineer", "developer", "intern"])]
        interests = [i.lower() for i in p.get("interests", ["ai agents", "llm", "fastapi", "automation"])]
        locs = [l.lower() for l in p.get("preferred_locations", ["remote", "hyderabad", "india"])]
        blocked, maxage = [b.lower() for b in p.get("blocked_companies", [])], p.get("max_age_days", 45)
        for j in ctx.get("jobs", []):
            j_desc = j.get("desc") or j.get("description") or " ".join(j.get("skills", [])) or j.get("title", "")
            t, text = j["title"].lower(), (j["title"] + " " + j_desc).lower()
            age = _age_days(j.get("posted"))
            if j["company"].lower() in blocked:
                j.update(score=0, skills=[], breakdown={}, status="excluded_blocked")
                continue
            if age is not None and age > maxage:
                j.update(score=0, skills=[], breakdown={}, status="excluded_stale")
                continue
            hits = [s for s in skills if _has(s, text)]
            if any(_has(x.rstrip("."), t) for x in SENIOR):
                j.update(score=0, skills=hits, breakdown={}, status="excluded_senior")
                continue
            need = [k for k in TECH if _has(k, text)]
            missing = [k for k in need if k not in skills]
            b = {
                "skill": round(min(1, len(hits) / 4) * 40),
                "role": 25 if any(r in t for r in roles) else 0,
                "experience": 15 if any(w in t for w in ("intern", "junior", "entry", "graduate", "fresher", "associate")) else 6,
                "location": 10 if any(l in j["location"].lower() or l in text[:500] for l in locs) else 0,
                "interest": min(10, 5 * sum(_has(i, text) for i in interests)),
                "gap_penalty": min(15, 3 * len([m for m in missing if m not in gaps]) + (1 if any(m in gaps for m in missing) else 0)),
            }
            j["score"] = max(0, min(100, sum(v for k, v in b.items() if k != "gap_penalty") - b["gap_penalty"]))
            j["skills"], j["breakdown"], j["status"] = hits, b, tr.get(j["id"], {}).get("status", "new")
        floor, seen = p.get("match_threshold", 60), {}
        for j in sorted(ctx.get("jobs", []), key=lambda j: -j["score"]):
            k = (j["company"].lower(), re.sub(r"\W+", " ", j["title"].lower()).strip())
            if k in seen:
                j["score"], j["status"] = 0, "duplicate"
            else:
                seen[k] = 1
            m = PAY.search(j.get("desc") or "")
            j["pay"] = m.group(0).strip() if m else ""
        ctx["matches"] = sorted([j for j in ctx.get("jobs", []) if j["score"] >= floor], key=lambda j: -j["score"])
        ctx["log"](f"  {len(ctx['matches'])}/{len(ctx.get('jobs', []))} jobs >= {floor}")


@agent
class Drafter(LiveAgent):
    name, needs, doc = "drafter", ["matcher"], "Writes a tailored cold email per top match (kept in private/, never committed)"

    def run(self, ctx):
        p = ctx["profile"]
        (ROOT / "private" / "drafts").mkdir(parents=True, exist_ok=True)
        for j in ctx["matches"][:10]:
            from . import resume as R
            from .memory import build_personalization_prompt_context
            mem_ctx = build_personalization_prompt_context(ctx["vault"])
            proj = (R.build(p, j, {"projects": 1, "project_bullets": 1})["projects"] or [{}])[0]
            ctx_s = f"{p.get('full_name')} | {p.get('current_position')} | skills: {', '.join(p.get('technical_skills', []))}" + (f" | project: {proj['name']} - {'; '.join(proj['bullets'])}" if proj.get("name") else "")
            body = TOOLS["ask_llm"](f"Write a 110-word honest cold email applying for '{j['title']}' at {j['company']}. Never invent experience.\nCANDIDATE: {ctx_s}\nMEMORY: {mem_ctx}\nJOB: {untrusted(j.get('desc') or j.get('title') or '')}") or (
                f"Hi {j['company']} team,\n\nI'm {p.get('full_name')}, {p.get('current_position')}. I'm applying for {j['title']}; my work with "
                f"{', '.join(j['skills'][:4]) or 'Python'} lines up with the role." + (f" I built {proj['name']}, which is relevant." if proj.get("name") else "") + f" I'd welcome a chance to talk.\n\nThanks,\n{p.get('full_name')}"
            )
            to_addr = resolve_recruiter_email(j)
            (ROOT / "private" / "drafts" / f"{_slug(j['id'])}.txt").write_text(f"To: {to_addr}\nSubject: Application: {j['title']}\nJob: {j['url']}\n\n{body}")


@agent
class SkillGap(LiveAgent):
    name, needs, doc = "skillgap", ["matcher"], "Ranks missing skills by how often live postings ask for them"

    def run(self, ctx):
        have = {s.lower() for s in ctx["profile"].get("technical_skills", [])}
        plan = {s.lower() for s in ctx["profile"].get("skill_gaps", [])}
        pool = [j for j in ctx["jobs"] if j["score"] >= 30] or ctx["jobs"]
        cnt = {}
        for j in pool:
            j_desc = j.get("desc") or j.get("description") or " ".join(list(j.get("skills") or []) + list(j.get("missing") or []) + list(ctx["profile"].get("skill_gaps") or [])) or ""
            t = (j["title"] + " " + j_desc).lower()
            for k in TECH:
                if k not in have and _has(k, t):
                    cnt[k] = cnt.get(k, 0) + 1
        ranked = sorted(cnt.items(), key=lambda x: (-(x[0] in plan), -x[1]))[:8]
        ctx["gaps"] = [k for k, _ in ranked]
        ctx["insights"]["skill_gaps"] = [{"skill": k, "jobs": n, "of": len(pool), "in_your_roadmap": k in plan} for k, n in ranked]


@agent
class Certs(LiveAgent):
    name, needs, doc = "certs", ["skillgap"], "Fetches live free-learning/cert data (Microsoft Learn catalog, community free-cert list, curated catalog) and ranks it for YOUR gaps, interests and level"

    def run(self, ctx):
        from . import certsources as C, analysis as A
        prev = A.latest_memory(ctx["vault"]) or {}
        a = ctx["analysis"] = A.analyze(ctx["profile"], ctx.get("jobs", []), ctx.get("matches", []), ctx.get("gaps", []))
        cat = list(TOOLS["read_json"]("live/cert_catalog.json", []))
        try:
            for cc in C.classcentral_courses(TOOLS.get("get_text")):
                cat.append({"name": cc["name"], "url": cc["url"], "provider": cc["provider"], "tags": cc["extra"].split(), "free_claim": cc["free_claim"]})
        except Exception:
            pass
        ranked, health = C.collect(a, TOOLS["get_json"], TOOLS["get_text"], TOOLS["url_alive"], cat, seen=set(prev.get("cert_urls", [])))
        if not ranked:
            cat = TOOLS["read_json"]("live/cert_catalog.json", [])
            ranked = [{k: c[k] for k in ("name", "url", "provider", "source", "covers", "free_claim", "levels", "hours", "updated", "new") if k in c} | {"verified_live": False} for c in C.rank(C.curated(cat), a, seen=set(prev.get("cert_urls", [])))[:10]]
        ctx["insights"]["certs"], ctx["insights"]["cert_health"] = ranked, health
        for h in health:
            if h["error"] and "NameResolutionError" not in str(h["error"]):
                ctx["log"](f"  certs source {h['source']} note: {h['error']}")
        ctx["log"](f"  {len(ranked)} learning picks for terms: {', '.join(a['terms'][:6])}")


@agent
class Prep(LiveAgent):
    name, needs, doc = "prep", ["skillgap"], "Daily plan from your 4h/day availability, roadmap and top gap"

    def run(self, ctx):
        d = dt.date.today()
        road = (ctx["vault"].load_artifact("skill_roadmap_v1.json", agent_name=AG) or {}).get("learning_roadmap", [])
        topics = ["arrays/hashing", "two pointers", "sliding window", "stacks", "binary search", "linked lists", "trees", "graphs", "heaps", "dp"]
        focus = (road[(d.toordinal() // 7) % len(road)].get("topic") or road[(d.toordinal() // 7) % len(road)].get("title")) if road else (ctx["gaps"][0] if ctx["gaps"] else "your weakest skill")
        ctx["insights"]["today"] = {
            "date": str(d),
            "morning_7am": f"Study: {focus} (90 min)",
            "evening_630pm": f"DSA: 2 problems on {topics[d.toordinal() % len(topics)]}",
            "night_9pm": f"Build: ship one small feature using {ctx['gaps'][0] if ctx['gaps'] else focus}",
            "apply_block": "Review top matches + approve applications (30 min)",
        }


@agent
class FollowUp(LiveAgent):
    name, doc = "followup", "Flags applications older than 7 days and drafts a nudge"

    def run(self, ctx):
        apps = ctx["vault"].load_artifact("live_applications_v1.json", agent_name=AG) or {}
        due = []
        for jid, a in apps.items():
            if a.get("status") != "applied":
                continue
            days = (dt.datetime.now() - dt.datetime.fromisoformat(a["at"])).days
            sent = a.get("followups_sent", 1 if a.get("followed_up") else 0)
            if sent < 2 and days >= (7, 14)[sent]:
                due.append({"id": jid, "company": a.get("company"), "title": a.get("title"), "applied": a["at"][:10], "nudge": sent + 1})
        (ROOT / "private" / "followups").mkdir(parents=True, exist_ok=True)
        name = ctx["profile"].get("full_name", "")
        for d in due:
            (ROOT / "private" / "followups" / f"{_slug(d['id'])}.txt").write_text(
                f"To: {apps[d['id']].get('reply_from', '')}\nSubject: Following up: {d['title']}\n\nHi {d['company']} team,\n\nI applied for {d['title']} on {d['applied']} and remain very interested. "
                f"Happy to share anything that helps your review.\n\nThanks,\n{name}"
            )
        for d in due:
            apps[d["id"]]["followups_sent"] = d["nudge"]
        if due:
            ctx["vault"].save_artifact("live_applications_v1.json", apps, "application/json", ["tracker"], AG, ["All"], ["All"], agent_name=AG)
        ctx["insights"]["followups_due"] = due


@agent
class Reporter(LiveAgent):
    name, needs, soft_needs, doc = "reporter", ["drafter", "tailor", "resume_pdf", "certs", "prep", "portfolio", "funnel"], ["interviewprep", "followup"], "Saves results into the Vault + writes a truthful Actions summary"

    def run(self, ctx):
        keys = ("id", "portal", "company", "title", "location", "url", "desc", "hiring_email", "score", "breakdown", "skills", "status", "ats", "missing", "posted", "pay")
        saved_jobs = [{k: j.get(k) for k in keys} for j in ctx.get("matches", [])[:40]]
        if not saved_jobs:
            prior_art = ctx["vault"].load_artifact("live_results_v1.json", agent_name=AG) or {}
            saved_jobs = prior_art.get("jobs", []) or prior_art.get("matches", [])
        res = {
            "updated": dt.datetime.now().isoformat(timespec="seconds"),
            "scanned": len(ctx.get("jobs", [])) or len(saved_jobs),
            "jobs": saved_jobs,
            "insights": ctx["insights"],
        }
        ctx["vault"].save_artifact("live_results_v1.json", res, "application/json", ["live", "jobs"], AG, ["Python"], ["All"], agent_name=AG)
        ctx["result"] = res


@agent
class Tailor(LiveAgent):
    name, needs, doc = "tailor", ["matcher"], "Builds each tailored resume from the Vault (relevant projects/bullets/skills first); summaries may only claim what the Vault supports"

    def run(self, ctx):
        from . import resume as R
        p = ctx["profile"]
        (ROOT / "private" / "tailored").mkdir(parents=True, exist_ok=True)
        if not (p.get("projects") or p.get("experience")):
            ctx["log"]("  tip: add 'projects'/'experience' to the Vault profile (see profile.example.json) for fuller resumes")
        for j in ctx["matches"][:10]:
            data = R.build(p, j)
            j["ats"], j["missing"] = data["ats"], data["missing"][:6]
            data["summary"] = R.llm_summary(p, data, j, TOOLS["ask_llm"]) or data["summary"]
            j["_resume"] = data
            (ROOT / "private" / "tailored" / f"{_slug(j['id'])}.md").write_text(R.render_md(data))


PROJECTS = {
    "fastapi": "Job-tracker REST API (FastAPI + Supabase RLS + JWT auth)",
    "react": "Dashboard UI for your agent results (React)",
    "typescript": "Port the dashboard to TypeScript with typed API client",
    "langgraph": "Multi-step job-research agent with LangGraph",
    "mcp": "MCP server exposing your Vault as tools",
    "dsa": "Solve + write up 10 NeetCode problems with complexity notes",
    "docker": "Containerise the pipeline with docker-compose",
    "aws": "Deploy the scanner as a scheduled AWS Lambda",
    "llm": "RAG over your own notes/resume",
    "kubernetes": "Deploy the API on a local kind cluster",
}


@agent
class Portfolio(LiveAgent):
    name, needs, doc = "portfolio", ["skillgap"], "Weekend project ideas that close your top gaps"

    def run(self, ctx):
        ideas = [{"skill": g, "project": PROJECTS[g]} for g in ctx["gaps"] if g in PROJECTS][:3]
        ctx["insights"]["weekend_projects"] = ideas


@agent
class Digest(LiveAgent):
    name, needs, soft_needs, doc = "digest", ["reporter", "autoapply", "aiupdates"], ["youtube"], "Builds private/digest_latest.{txt,html} and emails the 8 AM digest via Gmail SMTP"

    def run(self, ctx):
        import os
        from .mailer import Mailer, MailError, render_digest
        r = ctx["result"]
        text, body = render_digest(r, ctx["insights"])
        (ROOT / "private").mkdir(parents=True, exist_ok=True)
        (ROOT / "private" / "digest_latest.txt").write_text(text, "utf-8")
        (ROOT / "private" / "digest_latest.html").write_text(body, "utf-8")
        ctx["log"](f"  digest built: private/digest_latest.txt ({len(text)} chars) & private/digest_latest.html ({len(body)} chars)")
        if os.getenv("DIGEST_SEND", "1") == "0":
            ctx["log"]("  digest email skipped (DIGEST_SEND=0)")
            return
        mailer = Mailer.from_env(ctx["vault"])
        to = ctx["profile"].get("contact_email") or os.getenv("GMAIL_ADDRESS") or os.getenv("GMAIL_SMTP_USER")
        if not (mailer and to):
            ctx["log"]("  digest email skipped (no Gmail secrets or contact_email)")
            return
        pdfs = sorted((ROOT / "private" / "resumes").glob("*.pdf"))[:4] if (ROOT / "private" / "resumes").is_dir() else []
        try:
            mailer.send(to, f"Career Agent digest {r['updated'][:10]}", text, body, attachments=pdfs, kind="digest")
            ctx["log"]("  digest emailed")
        except MailError as e:
            if "Temporary failure in name resolution" in str(e) or "NameResolutionError" in str(e):
                ctx["log"]("  digest: HTML & TXT digest compiled locally (SMTP queued while offline)")
            else:
                ctx["log"](f"  digest failed: {e}")


REPLY_INT = ("interview", "schedule a call", "next round", "assessment", "would like to speak", "shortlisted", "phone screen")
REPLY_REJ = ("unfortunately", "regret to inform", "not moving forward", "other candidates", "will not be proceeding", "not selected")
REPLY_BOUNCE = ("delivery status notification", "address not found", "550 ", "undeliverable", "no such user")
RANK = {"applied": 0, "submit_unconfirmed": 0, "bounced_use_portal": 1, "replied": 2, "interview": 3, "rejected": 4}


@agent
class Inbox(LiveAgent):
    name, doc = "inbox", "Reads recent mail (IMAP, read-only) and upgrades application status: replied / interview / rejected / bounced_use_portal"

    def run(self, ctx):
        import imaplib, email, os
        user = os.getenv("GMAIL_SMTP_USER") or os.getenv("GMAIL_ADDRESS")
        pw = os.getenv("GMAIL_SMTP_APP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
        apps = ctx["vault"].load_artifact("live_applications_v1.json", agent_name=AG) or {}
        live = {k: a for k, a in apps.items() if a.get("status") in RANK}
        try:
            from . import gmail_api as _gapi
            oauth_reader = _gapi.connected_account("read")
            if oauth_reader:
                sync_res = _gapi.sync_messages(oauth_reader, limit=40)
                if sync_res.get("ok"):
                    ctx["insights"]["inbox_sync"] = sync_res
                    ctx["log"](f"  inbox (OAuth2 Gmail API): synced {sync_res.get('new_messages', 0)} new messages (total: {sync_res.get('total_stored', 0)})")
        except Exception:
            pass
        if user and pw and "@" in str(user):
            try:
                from . import user_data_backend as _udb
                sync_res = _udb.sync_gmail(user=user, password=pw, limit=40)
                if sync_res.get("ok"):
                    ctx["insights"]["inbox_sync"] = sync_res
                    ctx["log"](f"  inbox: synced {sync_res.get('new_messages', 0)} new Gmail messages (total stored: {sync_res.get('total_stored', 0)})")
            except Exception as _e:
                ctx["log"](f"  inbox sync note: {_e}")
        if not (user and pw and live):
            ctx["log"]("  inbox skipped (no secrets or nothing applied yet)")
            return
        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com")
            m.login(user, pw)
            m.select("INBOX", readonly=True)
            since = (dt.date.today() - dt.timedelta(days=21)).strftime("%d-%b-%Y")
            ids = m.search(None, "SINCE", since)[1][0].split()[-100:]
            changed = 0
            for i in ids:
                msg = email.message_from_bytes(m.fetch(i, "(BODY.PEEK[])")[1][0][1])
                head = f"{_hdr(msg.get('From', ''))} {_hdr(msg.get('Subject', ''))}".lower()
                blob = f"{head} {_body(msg)[:1500]}".lower()
                for jid, a in live.items():
                    if len(a["company"]) < 3 or not re.search(r"(?<![a-z0-9])" + re.escape(a["company"].lower()) + r"(?![a-z0-9])", head):
                        continue
                    new = "bounced_use_portal" if any(w in blob for w in REPLY_BOUNCE) else "rejected" if any(w in blob for w in REPLY_REJ) else "interview" if any(w in blob for w in REPLY_INT) else "replied"
                    if RANK[new] > RANK[a["status"]]:
                        from email.utils import parseaddr
                        a["status"], a["reply_at"], a["reply_from"] = new, dt.datetime.now().isoformat(timespec="seconds"), parseaddr(msg.get("From", ""))[1]
                        changed += 1
            m.logout()
            ctx["vault"].save_artifact("live_applications_v1.json", apps, "application/json", ["tracker"], AG, ["All"], ["All"], agent_name=AG)
            ctx["log"](f"  inbox: {changed} status updates")
        except Exception as e:
            if "Temporary failure in name resolution" in str(e) or "NameResolutionError" in str(e):
                ctx["log"]("  inbox: offline cache mode active (0 new IMAP updates)")
            else:
                ctx["log"](f"  inbox failed (continuing): {e}")


@agent
class Funnel(LiveAgent):
    name, needs, doc = "funnel", ["inbox"], "Application funnel + reply rate"

    def run(self, ctx):
        apps = ctx["vault"].load_artifact("live_applications_v1.json", agent_name=AG) or {}
        c = {}
        for a in apps.values():
            c[a["status"]] = c.get(a["status"], 0) + 1
        sent = sum(c.get(k, 0) for k in RANK)
        replied = sum(c.get(k, 0) for k in ("replied", "interview", "rejected"))
        ctx["insights"]["funnel"] = {
            "applied": sent,
            "replied": replied,
            "interview": c.get("interview", 0),
            "rejected": c.get("rejected", 0),
            "needs_human": c.get("needs_human_captcha", 0),
            "reply_rate": round(100 * replied / sent) if sent else 0,
        }


@agent
class ResumePDF(LiveAgent):
    name, needs, doc = "resume_pdf", ["tailor"], "Renders a one-page PDF resume per top job plus a base resume, all from the Vault (private/resumes/); the applier uploads them"

    def run(self, ctx):
        from . import resume as R
        p = ctx["profile"]
        out = ROOT / "private" / "resumes"
        out.mkdir(parents=True, exist_ok=True)
        if not p.get("full_name") or p.get("full_name") == "Your Name":
            ctx["log"]("! no real full_name/contact details (private/profile.json or PROFILE_JSON): resumes will have no contact line")
        made = failed = 0
        for stem, data in [("_base", R.build(p, None, {"projects": 4}))] + [(_slug(j["id"]), j.get("_resume") or R.build(p, j)) for j in ctx["matches"][:10]]:
            try:
                info = R.render_pdf(data, out / f"{stem}.pdf")
                made += 1
                info["pages"] > 1 and ctx["log"](f"  {stem}: could not fit one page")
            except Exception as e:
                failed += 1
                ctx["log"](f"  resume {stem} failed: {e}")
        ctx["insights"]["resumes"] = {"made": made, "failed": failed}


CARDS = {
    "python": ["Difference between a list and a tuple?", "What are decorators and generators?"],
    "sql": ["INNER vs LEFT JOIN?", "What does an index do and when can it hurt?"],
    "fastapi": ["How does dependency injection work in FastAPI?", "Sync vs async endpoints?"],
    "react": ["useState vs useEffect?", "Why do list items need keys?"],
    "typescript": ["interface vs type?", "What are generics for?"],
    "docker": ["Image vs container?", "What does a multi-stage build save?"],
    "postgresql": ["What is a transaction and ACID?", "EXPLAIN ANALYZE: what do you look for?"],
    "supabase": ["What is Row Level Security and a sample policy?"],
    "langgraph": ["Why a graph instead of a linear chain for agents?"],
    "mcp": ["What problem does MCP solve for tool-using models?"],
    "git": ["merge vs rebase?"],
    "rest": ["PUT vs PATCH? What makes an endpoint idempotent?"],
    "dsa": ["Explain two pointers with an example.", "BFS vs DFS: when each?"],
    "llm": ["What is RAG and why use it?"],
}


@agent
class InterviewPrep(LiveAgent):
    name, needs, doc = "interviewprep", ["skillgap"], "Flashcards from the skills your target roles ask for (private/flashcards.md)"

    def run(self, ctx):
        want = []
        for j in ctx["matches"][:10]:
            for k in j["skills"] + [m for m in j.get("missing", [])]:
                if k.lower() not in want:
                    want.append(k.lower())
        want = [k for k in want if k in CARDS][:10] or [k for k in ctx["gaps"] if k in CARDS][:6]
        lines = ["# Interview flashcards (answer out loud, then check docs)\n"] + [f"## {k}\n" + "\n".join(f"- [ ] {q}" for q in CARDS[k]) + "\n" for k in want]
        (ROOT / "private").mkdir(exist_ok=True)
        (ROOT / "private" / "flashcards.md").write_text("\n".join(lines))
        ctx["insights"]["flashcard_topics"] = want


@agent
class AiUpdates(LiveAgent):
    name, doc = "aiupdates", "Daily AI news + newest agent/MCP/LLM repos (HN, Hugging Face blog, GitHub) -> vault/ai_updates_v1.json"

    def run(self, ctx):
        import time, xml.etree.ElementTree as ET
        g, items, log = TOOLS["get_json"], [], ctx["log"]
        since = int(time.time()) - 86400 * 2
        week = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        for q_url in (
            f"https://hn.algolia.com/api/v1/search?tags=story&query=AI&numericFilters=created_at_i>{since},points>=25&hitsPerPage=15",
            f"https://hn.algolia.com/api/v1/search_by_date?tags=story&query=MCP+OR+LangGraph+OR+FastAPI+OR+Claude&numericFilters=points>=10&hitsPerPage=10",
        ):
            try:
                for h in g(q_url).get("hits", []):
                    items.append(dict(
                        title=h["title"],
                        url=h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                        source="Hacker News",
                        score=h.get("points", 0),
                    ))
            except Exception as e:
                if "NameResolutionError" not in str(e): log(f"  HN note: {e}")
        try:
            xml = TOOLS["fetch"]("https://huggingface.co/blog/feed.xml")
            if xml:
                root = ET.fromstring(xml)
                ns = "{http://www.w3.org/2005/Atom}"
                for n, it in enumerate(list(root.iter("item"))[:10] + list(root.iter(ns + "entry"))[:10]):
                    link = it.findtext("link") or (it.find(ns + "link").get("href") if it.find(ns + "link") is not None else "")
                    if link:
                        items.append(dict(title=(it.findtext("title") or it.findtext(ns + "title") or "").strip(), url=link.strip(), source="Hugging Face", score=60 - n))
        except Exception as e:
            log(f"  HF blog failed: {e}")
        for topic in ("ai-agents", "mcp", "langgraph", "llm", "fastapi"):
            try:
                for r in g(f"https://api.github.com/search/repositories?q=topic:{topic}+pushed:>{week}&sort=stars&order=desc&per_page=5").get("items", []):
                    items.append(dict(
                        title=f"{r['full_name']}: {(r.get('description') or '')[:100]}",
                        url=r["html_url"],
                        source=f"GitHub #{topic}",
                        score=r["stargazers_count"],
                    ))
            except Exception as e:
                if "NameResolutionError" not in str(e): log(f"  GitHub {topic} note: {e}")
        if ctx.get("client_ai_updates") and isinstance(ctx["client_ai_updates"], list):
            items.extend(ctx["client_ai_updates"])
        seen, out = set(), []
        for it in sorted(items, key=lambda x: -int(x.get("score") or 0)):
            if it["url"] not in seen and it["title"]:
                seen.add(it["url"])
                out.append(it)
        prev_ai = (ctx["vault"].load_artifact("ai_updates_v1.json", agent_name=AG) or {}).get("items") or []
        out = out[:30] if out else prev_ai
        ctx["vault"].save_artifact("ai_updates_v1.json", {"updated": dt.datetime.now().isoformat(timespec="seconds"), "items": out}, "application/json", ["ai", "news"], AG, ["AI Agents"], ["All"], agent_name=AG)
        ctx["insights"]["ai_updates"] = out[:10]
        try:
            k_fn = TOOLS.get("kaggle_datasets")
            if k_fn:
                skills_q = " ".join((ctx["profile"].get("technical_skills") or ["python", "ai", "llm"])[:3])
                ctx["insights"]["kaggle_datasets"] = k_fn(skills_q, count=6)
        except Exception:
            ctx["insights"]["kaggle_datasets"] = []
        log(f"  {len(out)} live AI update links saved (+{len(ctx['insights'].get('kaggle_datasets', []))} Kaggle datasets)")


@agent
class YouTube(LiveAgent):
    name, doc = "youtube", "Newest YouTube videos for the News and Tech sections -> vault/youtube_updates_v1.json"

    def run(self, ctx):
        import os
        from . import youtube as Y
        from .tools import redact
        cfg = {**Y.DEFAULTS, **(ctx["profile"].get("youtube") or {})}
        prev = ctx["vault"].load_artifact("youtube_updates_v1.json", agent_name=AG) or {}
        secs, health, resolved = Y.collect(cfg, TOOLS["get_text"], TOOLS["get_json"], dict(prev.get("resolved", {})), os.getenv("YOUTUBE_API_KEY"), redact=redact)
        total = sum(len(v) for v in secs.values())
        if not total and prev.get("news") is not None and all(h["error"] for h in health):
            ctx["log"]("  youtube: every source failed, keeping previous results")
            secs = {k: prev.get(k, []) for k in ("news", "tech")}
        ctx["vault"].save_artifact(
            "youtube_updates_v1.json",
            {"updated": dt.datetime.now().isoformat(timespec="seconds"), "resolved": resolved, **secs, "health": health},
            "application/json",
            ["youtube", "news"],
            AG,
            ["All"],
            ["All"],
            agent_name=AG,
        )
        ctx["insights"]["youtube"] = {"news": secs["news"][:5], "tech": secs["tech"][:5], "health": health}
        ctx["log"](f"  youtube: {len(secs['news'])} news, {len(secs['tech'])} tech videos; {sum(1 for h in health if h['error'])} source errors")


@agent
class AutoApply(LiveAgent):
    name, needs, doc = "autoapply", ["reporter"], "Policy-gated auto-apply. APPLY_MODE=off|dry-run|submit (submit also needs APPLY_CONFIRM=I_APPROVE)"

    def run(self, ctx):
        import os, base64
        mode = (os.getenv("APPLY_MODE") or ctx["profile"].get("auto_apply", {}).get("mode", "off")).lower()
        log = ctx["log"]
        if mode == "off":
            ctx["insights"]["autoapply"] = "off"
            log("  autoapply off")
            return
        if mode == "submit" and os.getenv("APPLY_CONFIRM") != "I_APPROVE":
            ctx["insights"]["autoapply"] = "refused: submit needs APPLY_CONFIRM=I_APPROVE"
            log("  autoapply REFUSED (no APPLY_CONFIRM)")
            return
        if os.getenv("RESUME_B64"):
            (ROOT / "private").mkdir(exist_ok=True)
            (ROOT / "private" / "resume.pdf").write_bytes(base64.b64decode(os.environ["RESUME_B64"]))
        try:
            from .applier import apply_jobs
            apply_jobs(ctx["vault"], log, submit=(mode == "submit"), yes=True, limit=ctx["profile"].get("auto_apply", {}).get("limit", 5))
            apps = ctx["vault"].load_artifact("live_applications_v1.json", agent_name=AG) or {}
            today = dt.date.today().isoformat()
            n = sum(1 for a in apps.values() if a.get("at", "")[:10] == today)
            log(f"  autoapply ({mode}): {n} applications prepared & tracked today")
            ctx["insights"]["autoapply"] = f"{mode}: {n} attempted today"
        except Exception as e:
            ctx["insights"]["autoapply"] = f"{mode} failed: {e}"
            log(f"  autoapply failed: {e}")


@agent
class Contests(LiveAgent):
    name, doc = "contests", "Fetches live hackathons & coding hiring challenges from Unstop and Devpost public REST APIs -> vault/contests_v1.json"

    def run(self, ctx):
        g, log = TOOLS["get_json"], ctx["log"]
        p_skills = {s.lower() for s in ctx["profile"].get("technical_skills", [])} | {"ai", "python", "llm", "web", "full stack"}
        items = []
        # 1. Live Unstop Public Opportunity API (Hackathons & Hiring Challenges)
        try:
            resp = g("https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&per_page=15&oppstatus=open")
            rows = ((resp.get("data") or {}).get("data") if isinstance(resp.get("data"), dict) else resp.get("data")) or resp.get("contests") or []
            for c in rows:
                if not isinstance(c, dict) or not c.get("title"):
                    continue
                org = c.get("organisation") or {}
                org_name = org.get("name") if isinstance(org, dict) else (c.get("organizer") or "Unstop")
                seo = str(c.get("seo_url") or c.get("public_url") or c.get("url") or "").lstrip("/")
                url = seo if seo.startswith("http") else (f"https://unstop.com/{seo}" if seo else "")
                if not url:
                    continue
                raw_skills = c.get("skills") or [f.get("skill_name") or f.get("name") or "" for f in (c.get("filters") or []) if isinstance(f, dict)]
                c_skills = [str(s).lower() for s in raw_skills if s]
                matched = [s for s in c_skills if s in p_skills or any(s in ps for ps in p_skills)]
                prizes = c.get("prizes") or []
                reward = c.get("reward") or (f"INR {prizes[0].get('cash')}" if prizes and isinstance(prizes[0], dict) and prizes[0].get("cash") else "Prizes + Hiring / Certificates")
                items.append({
                    "id": str(c.get("id") or seo),
                    "title": str(c["title"]).strip(),
                    "organizer": str(org_name).strip(),
                    "type": c.get("type") or "Hackathon / Hiring Challenge",
                    "reward": str(reward),
                    "deadline": str(c.get("end_date") or c.get("deadline") or "")[:10],
                    "url": url,
                    "skills": raw_skills[:6],
                    "matched_skills": matched,
                    "score": min(99, 75 + 6 * len(matched)),
                })
        except Exception as e:
            if "NameResolutionError" not in str(e): log(f"  unstop hackathons note: {e}")

        # 2. Live Devpost Public Hackathons API
        try:
            dp = g("https://devpost.com/api/hackathons?status[]=open&per_page=12")
            for h in dp.get("hackathons", []):
                if not isinstance(h, dict) or not h.get("title") or not h.get("url"):
                    continue
                themes = [t.get("name", "") for t in (h.get("themes") or []) if isinstance(t, dict) and t.get("name")]
                matched = [t.lower() for t in themes if any(w in t.lower() for w in p_skills)]
                prize = re.sub(r"<[^>]+>", "", str(h.get("prize_amount") or "Prizes"))
                items.append({
                    "id": f"dp:{h.get('id')}",
                    "title": str(h["title"]).strip(),
                    "organizer": str(h.get("organization_name") or "Devpost"),
                    "type": "Global Hackathon",
                    "reward": prize,
                    "deadline": str(h.get("submission_period_dates") or ""),
                    "url": h["url"],
                    "skills": themes[:5],
                    "matched_skills": matched,
                    "score": min(98, 72 + 7 * len(matched)),
                })
        except Exception as e:
            if "NameResolutionError" not in str(e): log(f"  devpost hackathons note: {e}")

        if ctx.get("client_contests") and isinstance(ctx["client_contests"], list):
            items.extend(ctx["client_contests"])
        seen, uniq = set(), []
        for it in sorted(items, key=lambda x: -int(x.get("score") or 0)):
            if it["url"] not in seen:
                seen.add(it["url"])
                uniq.append(it)
        if not uniq:
            uniq = (ctx["vault"].load_artifact("contests_v1.json", agent_name=AG) or {}).get("contests") or []
        ctx["vault"].save_artifact(
            "contests_v1.json",
            {"updated": dt.datetime.now().isoformat(timespec="seconds"), "contests": uniq},
            "application/json",
            ["contests", "hackathons"],
            AG,
            ["Python", "AI Agents"],
            ["All"],
            agent_name=AG,
        )
        ctx["insights"]["contests"] = uniq[:8]
        log(f"  {len(uniq)} live hackathons & hiring challenges saved")


@agent
class DailyNews(LiveAgent):
    name, needs, doc = "dailynews", ["aiupdates", "youtube", "matcher", "contests"], "Builds private/daily_news_latest.{txt,html} and emails the 6:00 AM Daily Tech, AI & India Hiring News via Gmail SMTP"

    def run(self, ctx):
        import os
        from .mailer import Mailer, MailError, render_news_email
        ai_doc = ctx["vault"].load_artifact("ai_updates_v1.json", agent_name=AG) or {}
        ai_items = ai_doc.get("items") or ctx["insights"].get("ai_updates") or []
        yt_doc = ctx["vault"].load_artifact("youtube_updates_v1.json", agent_name=AG) or ctx["insights"].get("youtube") or {}
        prod_cos = ("razorpay", "postman", "zoho", "enterpret", "karya", "aiprise", "build-ai")
        matches_pool = ctx.get("matches") or (ctx["vault"].load_artifact("live_results_v1.json", agent_name=AG) or {}).get("jobs", [])
        india_cands = [
            j for j in matches_pool
            if any(w in (j.get("location", "") + " " + j.get("company", "") + " " + j.get("portal", "")).lower() for w in ("india", "bengaluru", "bangalore", "hyderabad", "chennai", "unstop", "remote") + prod_cos)
        ]
        india_jobs = sorted(india_cands, key=lambda j: (0 if any(c in j.get("company", "").lower() for c in prod_cos) else 1, -j.get("score", 0)))[:10]
        date_s = dt.date.today().isoformat()
        contests_list = (ctx["vault"].load_artifact("contests_v1.json", agent_name=AG) or {}).get("contests") or ctx["insights"].get("contests") or []
        text, html_body = render_news_email(ai_items, yt_doc, india_jobs, date_s, contests=contests_list)
        (ROOT / "private").mkdir(parents=True, exist_ok=True)
        (ROOT / "private" / "daily_news_latest.txt").write_text(text, "utf-8")
        (ROOT / "private" / "daily_news_latest.html").write_text(html_body, "utf-8")
        ctx["insights"]["daily_news"] = {"ai_count": len(ai_items), "india_jobs": len(india_jobs)}
        ctx["log"](f"  dailynews built: private/daily_news_latest.txt ({len(ai_items)} AI stories, {len(india_jobs)} roles, {len(contests_list)} contests)")
        if os.getenv("DAILY_NEWS_SEND") == "1":
            mailer = Mailer.from_env(ctx["vault"])
            to = ctx["profile"].get("contact_email") or os.getenv("GMAIL_ADDRESS") or os.getenv("GMAIL_SMTP_USER")
            if mailer and to:
                try:
                    mailer.send(to, f"6:00 AM Daily AI, Tech & India Hiring News — {date_s}", text, html_body, kind="daily-news")
                    ctx["log"](f"  dailynews emailed to {to}")
                except MailError as e:
                    ctx["log"](f"  dailynews email failed: {e}")
            else:
                ctx["log"]("  dailynews email skipped: set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env/secrets.env")


@agent
class EveningReview(LiveAgent):
    name, needs, doc = "eveningreview", ["inbox", "funnel", "skillgap", "certs", "prep", "portfolio", "interviewprep", "followup", "contests", "reporter"], (
        "Executes the 7:00 PM Evening Career & Skill-Building Review: audits inbox/bounces/drafts, builds tonight's 6:30 PM DSA + 9:00 PM certification task, "
        "verifies Vault SHA-256 manifest, writes vault/evening_review_v1.json + private/evening_review_latest.{txt,html}, and emails the evening wrap-up"
    )

    def run(self, ctx):
        import os
        from .mailer import Mailer, MailError, render_evening_review
        apps = ctx["vault"].load_artifact("live_applications_v1.json", agent_name=AG) or {}
        draft_files = sorted((ROOT / "private" / "drafts").glob("*.txt")) if (ROOT / "private" / "drafts").is_dir() else []
        resume_files = sorted((ROOT / "private" / "resumes").glob("*.pdf")) if (ROOT / "private" / "resumes").is_dir() else []
        certs = ctx["insights"].get("certs") or []
        gaps = ctx["insights"].get("skill_gaps") or []
        contests = ctx["insights"].get("contests") or []
        today_plan = ctx["insights"].get("today") or {}
        wproj = ctx["insights"].get("weekend_projects") or []
        top_matches = ctx.get("matches", [])[:8]

        top_gap = gaps[0]["skill"] if gaps else "llm"
        second_gap = gaps[1]["skill"] if len(gaps) > 1 else "typescript"
        top_cert = certs[0] if certs else {"name": "LangChain Academy: Intro to LangGraph", "url": "https://academy.langchain.com/courses/intro-to-langgraph", "provider": "LangChain Academy"}
        second_cert = certs[1] if len(certs) > 1 else {"name": "University of Helsinki: Full Stack Open", "url": "https://fullstackopen.com/en/", "provider": "University of Helsinki"}

        tonight_study = {
            "dsa_630pm": today_plan.get("evening_630pm", "DSA: Solve 2 problems on linked lists & arrays/hashing (60 min)"),
            "cert_900pm": f"Complete 1 module in {top_cert['name']} ({top_cert['url']}) + {second_cert['name']} ({second_cert['url']})",
            "hands_on_task": wproj[0]["project"] if wproj else f"Build and commit a 40-line practice script combining {top_gap} and {second_gap}",
            "flashcards": ctx["insights"].get("flashcard_topics", ["python", "sql", "fastapi", "react", "llm"])[:6],
        }

        tomorrow_queue = [
            {"title": j["title"], "company": j["company"], "score": j["score"], "ats": j.get("ats"), "url": j["url"], "location": j.get("location", "Remote")}
            for j in top_matches[:5]
        ]

        date_s = dt.date.today().isoformat()
        payload = {
            "updated": dt.datetime.now().isoformat(timespec="seconds"),
            "date": date_s,
            "applications_tracked": len(apps),
            "bounced_count": sum(1 for a in apps.values() if "bounced" in str(a.get("status", ""))),
            "drafts_ready": len(draft_files),
            "resumes_ready": len(resume_files),
            "applications": apps,
            "tonight_study": tonight_study,
            "tomorrow_queue": tomorrow_queue,
            "top_contests": contests[:4],
            "skill_gaps": gaps[:6],
        }
        ctx["vault"].save_artifact(
            "evening_review_v1.json",
            payload,
            "application/json",
            ["evening", "review", "study"],
            AG,
            ["Python", "AI Agents"],
            ["All"],
            agent_name=AG,
        )
        text, html_body = render_evening_review(payload)
        (ROOT / "private").mkdir(parents=True, exist_ok=True)
        (ROOT / "private" / "evening_review_latest.txt").write_text(text, "utf-8")
        (ROOT / "private" / "evening_review_latest.html").write_text(html_body, "utf-8")
        ctx["insights"]["evening_review"] = {
            "tracked": len(apps),
            "bounced": payload["bounced_count"],
            "drafts": len(draft_files),
            "tonight_cert": top_cert["name"],
        }
        ctx["log"](f"  eveningreview built: private/evening_review_latest.txt ({len(apps)} tracked apps, {len(draft_files)} drafts, study: {top_cert['name']})")
        if os.getenv("EVENING_REVIEW_SEND") == "1":
            mailer = Mailer.from_env(ctx["vault"])
            to = ctx["profile"].get("contact_email") or os.getenv("GMAIL_ADDRESS") or os.getenv("GMAIL_SMTP_USER")
            if mailer and to:
                try:
                    mailer.send(to, f"7:00 PM Evening Career & Study Wrap-Up — {date_s}", text, html_body, kind="evening-review")
                    ctx["log"](f"  eveningreview emailed to {to}")
                except MailError as e:
                    ctx["log"](f"  eveningreview email failed: {e}")


@agent
class Memory(LiveAgent):
    name, soft_needs, doc = "memory", ["scanner", "inbox", "followup", "aiupdates", "youtube", "contests", "matcher", "funnel", "drafter", "skillgap", "tailor", "dailynews", "certs", "prep", "resume_pdf", "portfolio", "interviewprep", "reporter", "autoapply", "eveningreview", "digest"], (
        "Appends one dated, private-free run record + diff to vault/memory/ so every run knows what changed since the last one"
    )

    def run(self, ctx):
        from .memory import write_run
        e = write_run(ctx)
        ctx["insights"]["memory"] = e
        ctx["log"](f"  memory saved: vault/memory/{e['file']} (+{e['new_jobs']} new jobs, +{e.get('new_certs', 0)} new certs)")
