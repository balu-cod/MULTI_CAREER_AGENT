"""Per-run memory: one JSON (+ readable Markdown) file in vault/memory/ for every pipeline run, plus index.json and latest.json.
Holds the analysis of the user, what was fetched, what changed since last run, and any errors. Never contains contact details."""
import datetime as dt, json
from .analysis import SNAPSHOT_KEYS, latest_memory, memory_dir
from .tools import redact


def _write(vault, path, text): vault._atomic_write(path, text.encode("utf-8"))


def _markdown(m):
    u, j, A = m["user"], m["jobs"], m["analysis"]
    L = [f"# Run {m['run_id']}", "", f"- Finished: {m['finished']}  |  version {m['version']}  |  level: {A.get('level')}",
         f"- Jobs: {j['scanned']} scanned, {j['matched']} matched, **{j['new_since_last_run']} new** since last run",
         f"- Strengths: {', '.join(A.get('strengths', [])) or 'n/a'}", f"- Learning focus: {', '.join(A.get('terms', [])[:6]) or 'n/a'}", "", "## Top jobs"]
    L += [f"- {x['score']}  [{x['title']} @ {x['company']}]({x['url']}){' (new)' if x['new'] else ''}" for x in j["top"][:10]] or ["- none"]
    L += ["", "## Learning picks"] + ([f"- [{c['name']}]({c['url']}) ({c['provider']}; {c['free_claim']}){' (new)' if c.get('new') else ''}" for c in m["certs"]] or ["- none"])
    L += ["", "## Today", *[f"- {v}" for k, v in (m["today"] or {}).items() if k != "date"]]
    if m["errors"]: L += ["", "## Problems"] + [f"- {e}" for e in m["errors"]]
    return "\n".join(L) + "\n"


def write_run(ctx):
    vault = ctx["vault"]; mdir = memory_dir(vault); mdir.mkdir(parents=True, exist_ok=True)
    prev = latest_memory(vault) or {}; ins = ctx["insights"]; prof = ctx["profile"]; now = dt.datetime.now(dt.timezone.utc)
    pub = vault.load_artifact("user_profile_v1.json") or {}
    matches = ctx.get("matches", []); ids = [j["id"] for j in matches]; old = set(prev.get("matched_ids", [])); new_ids = [i for i in ids if i not in old]
    certs = ins.get("certs", []); res = ctx.get("result") or {}
    errors = [f"agent failed or skipped: {n}" for n in sorted(ctx.get("failed", []))]
    for key in ("source_health", "cert_health"):
        errors += [f"{key}: {h['source']}: {h['error']}" for h in ins.get(key, []) if h.get("error")]
    errors += [f"youtube: {h['source']}: {h['error']}" for h in (ins.get("youtube") or {}).get("health", []) if h.get("error")]
    errors += ["all job sources returned zero postings"] if ins.get("source_health") and not ctx.get("jobs") else []
    run_id = ctx.get("run_id") or now.strftime("%Y%m%dT%H%M%SZ")
    run = {"run_id": run_id, "started": (ctx.get("started") or now).isoformat(timespec="seconds"), "finished": now.isoformat(timespec="seconds"), "version": __import__("live").VERSION,
           "user": {k: pub.get(k, prof.get(k)) for k in SNAPSHOT_KEYS if k in pub or k in prof}, "analysis": ctx.get("analysis", {}),
           "jobs": {"scanned": len(ctx.get("jobs", [])), "matched": len(matches), "new_since_last_run": len(new_ids), "gone_since_last_run": len(old - set(ids)) if old else 0,
                    "sources": ins.get("source_health", []),
                    "top": [{"id": j["id"], "title": j["title"], "company": j["company"], "score": j["score"], "url": j["url"], "posted": j.get("posted"), "ats": j.get("ats"),
                             "pay": j.get("pay"), "new": j["id"] in new_ids} for j in matches[:15]]},
           "market_demand": ins.get("skill_gaps", []), "certs": certs, "cert_sources": ins.get("cert_health", []), "today": ins.get("today"), "funnel": ins.get("funnel"),
           "followups_due": ins.get("followups_due", []), "youtube": {k: len((ins.get("youtube") or {}).get(k, [])) for k in ("news", "tech")},
           "matched_ids": ids, "cert_urls": list(dict.fromkeys(prev.get("cert_urls", []) + [c["url"] for c in certs]))[-300:], "errors": errors,
           "log": [redact(x)[:300] for x in ctx.get("run_log", [])][-200:]}
    base, n = f"run_{run_id}", 1
    while (mdir / (base + ".json")).exists(): n += 1; base = f"run_{run_id}_{n}"
    text = json.dumps(run, indent=2, ensure_ascii=False)
    _write(vault, mdir / (base + ".json"), text); _write(vault, mdir / (base + ".md"), _markdown(run)); _write(vault, mdir / "latest.json", text)
    idx_path = mdir / "index.json"
    try: idx = json.loads(idx_path.read_text("utf-8")).get("runs", []) if idx_path.exists() else []
    except json.JSONDecodeError: idx = []
    entry = {"file": base + ".json", "summary": base + ".md", "run_id": run_id, "finished": run["finished"], "scanned": run["jobs"]["scanned"], "matched": run["jobs"]["matched"],
             "new_jobs": run["jobs"]["new_since_last_run"], "new_certs": len([c for c in certs if c.get("url") not in set(prev.get("cert_urls", []))]), "top_learning": certs[0]["name"] if certs else None, "errors": len(errors)}
    idx = [entry] + idx; keep = int(prof.get("memory_keep", 90))
    for old_e in idx[keep:]:
        for f in (old_e["file"], old_e["summary"]):
            try: (mdir / f).unlink()
            except OSError: pass
    _write(vault, idx_path, json.dumps({"runs": idx[:keep]}, indent=2))
    return entry



DEFAULT_PERSONALIZATION_MEMORY = [
    {"id": "mem_stack", "category": "stack_preference", "fact": "Prioritize Python, FastAPI, React, SQL, LangGraph, Model Context Protocol (MCP), and Edge AI / SLM roles.", "updated": "2026-11-10"},
    {"id": "mem_proof", "category": "production_proof", "fact": "Highlight TIMS (Tailoring Inventory Management System) and File Shelf Tracker built during Software Developer Internship at Aditya Birla Garments Limited.", "updated": "2026-11-10"},
    {"id": "mem_loc", "category": "location_preference", "fact": "Target Bengaluru, Hyderabad, Chennai, and Remote India product companies and funded AI startups.", "updated": "2026-11-10"},
    {"id": "mem_tone", "category": "outreach_style", "fact": "Keep cold recruiter emails under 120 words, attach role-tailored 1-page ATS PDF resume, and link GitHub portfolio.", "updated": "2026-11-10"},
]


def load_personalization_memory(vault):
    """Load persistent user personalization memory facts from Vault."""
    try:
        data = vault.load_artifact("user_personalization_memory.json")
        if isinstance(data, dict) and isinstance(data.get("facts"), list) and data["facts"]:
            return data
    except Exception:
        pass
    payload = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "facts": list(DEFAULT_PERSONALIZATION_MEMORY),
    }
    try:
        vault.save_artifact("user_personalization_memory.json", payload, "application/json", ["memory", "personalization"], "LIVE_PIPELINE_AGENT", ["All"], ["All"], agent_name="LIVE_PIPELINE_AGENT")
    except Exception:
        pass
    return payload


def save_personalization_fact(vault, fact_text, category="preference", fact_id=None):
    """Add or update a persistent user personalization memory fact."""
    fact_text = str(fact_text or "").strip()
    if not fact_text:
        return load_personalization_memory(vault)
    cur = load_personalization_memory(vault)
    facts = list(cur.get("facts") or [])
    now_s = dt.date.today().isoformat()
    fid = fact_id or f"mem_{int(dt.datetime.now().timestamp())}_{len(facts)+1}"
    updated_existing = False
    for f in facts:
        if f.get("id") == fid or f.get("fact", "").lower() == fact_text.lower():
            f["fact"] = fact_text
            f["category"] = category
            f["updated"] = now_s
            updated_existing = True
            break
    if not updated_existing:
        facts.insert(0, {"id": fid, "category": str(category or "preference"), "fact": fact_text, "updated": now_s})
    payload = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "facts": facts[:50],
    }
    vault.save_artifact("user_personalization_memory.json", payload, "application/json", ["memory", "personalization"], "LIVE_PIPELINE_AGENT", ["All"], ["All"], agent_name="LIVE_PIPELINE_AGENT")
    return payload


def delete_personalization_fact(vault, fact_id):
    """Remove a personalization memory fact by ID."""
    cur = load_personalization_memory(vault)
    facts = [f for f in (cur.get("facts") or []) if f.get("id") != fact_id]
    payload = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "facts": facts,
    }
    vault.save_artifact("user_personalization_memory.json", payload, "application/json", ["memory", "personalization"], "LIVE_PIPELINE_AGENT", ["All"], ["All"], agent_name="LIVE_PIPELINE_AGENT")
    return payload


def build_personalization_prompt_context(vault):
    """Build a compact personalization string for LLM prompt injection."""
    try:
        mem = load_personalization_memory(vault)
        facts = [f.get("fact", "") for f in (mem.get("facts") or [])[:8] if f.get("fact")]
        return " | ".join(facts)
    except Exception:
        return ""
