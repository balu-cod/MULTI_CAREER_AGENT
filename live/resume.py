"""Vault-driven resume builder. Every fact on the page comes from the Vault profile (plus private contact details); nothing is invented.

Vault fields used (all optional except a name):
  technical_skills, skill_groups{label:[skills]}, current_position, summary, location, github, linkedin, portfolio, availability, education,
  experience[{role, company, period, location, bullets[], skills[]}], projects[{name, link, period, summary|bullets[], skills[]}],
  certifications[str | {name, issuer, year}], achievements[str]

build(profile, job)  -> structured dict (tailored to the job: relevant projects/bullets/skills first, extras trimmed)
render_pdf(data, path) -> one-page, single-column, ATS-friendly PDF (text shrinks, then least relevant items are dropped, until it fits)
render_md(data)      -> readable Markdown copy, with the 'do not claim' list for the job."""
import copy, html, io, re
from .terms import TECH, has_term

CATEGORIES = (
    ("Languages", {"python", "java", "javascript", "typescript", "c", "c++", "c#", "go", "golang", "rust", "php", "sql", "kotlin", "swift", "bash", "html", "html5", "css", "css3", "r"}),
    ("Frameworks & Libraries", {"react", "next.js", "node", "node.js", "fastapi", "django", "flask", "express", "spring", "vue", "angular", "bootstrap", "tailwind css", "tailwind", "rest", "graphql"}),
    ("Databases", {"postgresql", "mysql", "mongodb", "redis", "supabase", "sqlite", "firebase", "sql server"}),
    ("Cloud & DevOps", {"docker", "kubernetes", "aws", "azure", "gcp", "linux", "ci/cd", "github actions", "terraform", "nginx"}),
    ("AI & Data", {"langchain", "langgraph", "mcp", "llm", "rag", "pytorch", "tensorflow", "pandas", "numpy", "scikit-learn", "openai", "machine learning", "nlp"}),
)
LIMITS = {"projects": 3, "project_bullets": 3, "experience": 3, "experience_bullets": 4, "certifications": 4, "achievements": 3}


# ---------- vault data normalisation (accepts strings or dicts, tolerates missing keys) ----------
def _list(v): return v if isinstance(v, list) else ([] if v in (None, "", {}) else [v])
def _s(v): return str(v).strip() if v not in (None, "") else ""


def _bullets(item):
    b = [_s(x) for x in _list(item.get("bullets")) if _s(x)]
    return b or ([_s(item.get("summary"))] if _s(item.get("summary")) else [])


def _education(v):
    out = []
    for e in _list(v):
        if isinstance(e, dict): out.append({"text": ", ".join(x for x in (_s(e.get("degree")), _s(e.get("school")), _s(e.get("period")), _s(e.get("details"))) if x) or _s(e.get("text"))})
        elif _s(e): out.append({"text": _s(e)})
    return [e for e in out if e["text"]]


def _cert(c):
    if isinstance(c, dict): return " - ".join(x for x in (_s(c.get("name")), ", ".join(y for y in (_s(c.get("issuer")), _s(c.get("year"))) if y)) if x)
    return _s(c)


def skill_pool(p):
    """Skills the vault supports: technical_skills + skills named on experience/projects. The ONLY skills a resume may list or claim."""
    out = []
    for s in list(_list(p.get("technical_skills"))) + [x for it in _list(p.get("experience")) + _list(p.get("projects")) if isinstance(it, dict) for x in _list(it.get("skills"))]:
        if _s(s) and _s(s).lower() not in [o.lower() for o in out]: out.append(_s(s))
    return out


def job_text(job):
    if not job: return ""
    d = job.get("desc") or job.get("description") or " ".join(list(job.get("skills") or []) + list(job.get("missing") or [])) or ""
    return f"{job.get('title', '')} {d}".lower()


# ---------- relevance ----------
def _score(item, text, pool, job):
    if not text: return 0
    body = " ".join([_s(item.get("name") or item.get("role")), " ".join(_bullets(item)), " ".join(_s(x) for x in _list(item.get("skills")))]).lower()
    s = 3 * sum(has_term(x, text) for x in _list(item.get("skills")) if _s(x))
    s += 2 * sum(has_term(t, text) and has_term(t, body) for t in TECH) + sum(has_term(x, text) and has_term(x, body) for x in pool)
    s += sum(1 for w in re.findall(r"[a-z+#.]{3,}", (job or {}).get("title", "").lower()) if w not in ("and", "the", "for", "with") and w in body)
    return s


def _rank(items, text, pool, job, key=lambda x: x):
    scored = [(-_score(key(it), text, pool, job), n, it) for n, it in enumerate(items)]       # ties keep the vault's own order
    return [it for _, _, it in sorted(scored, key=lambda t: (t[0], t[1]))]


def top_bullets(item, text, pool, job, k):
    bl = _bullets(item); ranked = _rank(bl, text, pool, job, key=lambda b: {"bullets": [b], "skills": item.get("skills")})
    return ranked[:k]


def group_skills(p, pool, text):
    """[(label, [skills])]: skills the job mentions first inside each group, groups with most job hits first. Respects vault skill_groups."""
    cfg = p.get("skill_groups") if isinstance(p.get("skill_groups"), dict) else None
    if cfg: groups = [(k, [x for x in (_s(v) for v in _list(vs)) if x]) for k, vs in cfg.items()]
    else:
        groups = [(label, [s for s in pool if s.lower() in names]) for label, names in CATEGORIES]
    placed = {s.lower() for _, vs in groups for s in vs}; rest = [s for s in pool if s.lower() not in placed]
    if rest: groups.append(("Tools & Other" if not cfg else "Other", rest))
    out = []
    for n, (label, vs) in enumerate(groups):
        if vs: out.append((-sum(has_term(x, text) for x in vs) if text else 0, n, label, sorted(vs, key=lambda x: (not has_term(x, text) if text else False))))
    return [(label, vs) for _, _, label, vs in sorted(out, key=lambda t: (t[0], t[1]))]


# ---------- build ----------
def default_summary(p, job, hits, projects):
    cur = _s(p.get("current_position")); base = _s(p.get("summary"))
    if base and not job: return base
    top = ", ".join(hits[:6] or _list(p.get("technical_skills"))[:6])
    exp_list = [x for x in _list(p.get("experience")) if isinstance(x, dict) and _s(x.get("company"))]
    exp_str = f" with industry experience at {exp_list[0]['company']}" if exp_list else ""
    parts = []
    if base: parts.append(base)
    elif cur: parts.append(f"{cur}{exp_str}, specializing in {top}." if top else f"{cur}{exp_str}.")
    elif top: parts.append(f"Software engineering candidate skilled in {top}.")
    if len(projects) >= 2:
        parts.append(f"Architected and deployed {projects[0]['name']} and {projects[1]['name']}.")
    elif projects:
        parts.append(f"Architected and deployed {projects[0]['name']}.")
    if job and job.get("title"):
        avail = f" ({_s(p.get('availability'))})" if _s(p.get("availability")) else ""
        parts.append(f"Ready to contribute production-grade code as {job['title']}" + (f" at {job['company']}" if job.get("company") else "") + f"{avail}.")
    return " ".join(x for x in parts if x).strip()


def build(p, job=None, limits=None):
    lim = {**LIMITS, **(limits or {})}; text = job_text(job); pool = skill_pool(p)
    hits = [s for s in pool if has_term(s, text)] if text else []
    need = [k for k in TECH if has_term(k, text)] if text else []; have = {s.lower() for s in pool}; missing = [k for k in need if k not in have]
    projects = [{"name": _s(x.get("name")), "link": _s(x.get("link")), "period": _s(x.get("period")), "bullets": top_bullets(x, text, pool, job, lim["project_bullets"]), "skills": [_s(s) for s in _list(x.get("skills"))]}
                for x in _rank([x for x in _list(p.get("projects")) if isinstance(x, dict) and _s(x.get("name"))], text, pool, job)[:lim["projects"]]]
    exp = [{"role": _s(x.get("role")), "company": _s(x.get("company")), "period": _s(x.get("period")), "location": _s(x.get("location")), "bullets": top_bullets(x, text, pool, job, lim["experience_bullets"])}
           for x in _list(p.get("experience")) if isinstance(x, dict) and (_s(x.get("role")) or _s(x.get("company")))][:lim["experience"]]
    links = [(lab, u) for lab, u in (("GitHub", p.get("github")), ("LinkedIn", p.get("linkedin")), ("Portfolio", p.get("portfolio"))) if _s(u)]
    return {"name": _s(p.get("full_name")), "headline": _s(p.get("current_position")),
            "contact": [x for x in (_s(p.get("contact_email")), _s(p.get("contact_phone")), _s(p.get("location"))) if x], "links": links,
            "summary": default_summary(p, job, hits, projects), "skills": group_skills(p, pool, text), "experience": exp, "projects": projects,
            "education": _education(p.get("education")), "certifications": [c for c in (_cert(x) for x in _list(p.get("certifications"))) if c][:lim["certifications"] + 4],
            "achievements": [_s(a) for a in _list(p.get("achievements")) if _s(a)][:lim["achievements"]], "availability": _s(p.get("availability")),
            "ats": round(100 * len(hits) / max(1, len(hits) + len(missing))) if job else None, "matched": hits, "missing": missing,
            "job": {"id": job.get("id"), "title": job.get("title"), "company": job.get("company")} if job else None}


# ---------- truthful summaries ----------
def facts_text(p):
    return " ".join(str(v) for v in (p.get("current_position"), p.get("summary"), p.get("experience"), p.get("projects"), p.get("education"), p.get("certifications"), p.get("achievements"), p.get("technical_skills")))


def claims_ok(summary, p):
    """A generated summary is accepted only if it names no technology outside the vault and no number that is not in the vault."""
    pool = skill_pool(p); facts = facts_text(p).lower()
    if any(has_term(t, summary) and t not in {s.lower() for s in pool} and not has_term(t, facts) for t in TECH): return False
    return all(n.rstrip(".,") in facts for n in re.findall(r"\d[\d,.%]*", summary))


def llm_summary(p, data, job, ask):
    """2-3 sentence summary from Claude, restricted to vault facts; None when there is no key or the text makes an unsupported claim."""
    facts = {"current_position": data["headline"], "skills": [s for _, vs in data["skills"] for s in vs], "experience": data["experience"], "projects": [{"name": x["name"], "bullets": x["bullets"]} for x in data["projects"]]}
    out = ask(f"Write a 2-3 sentence resume summary (no first-person pronouns) for the role '{job.get('title')}' at {job.get('company')}. Use ONLY the facts below; never invent employers, "
              f"numbers, tools or experience. Output the summary text only.\nFACTS: {facts}", 300)
    out = re.sub(r"\s+", " ", out or "").strip()
    return out if out and len(out) < 700 and claims_ok(out, p) else None


def llm_tailor_resume(p, job=None, company_research=None, limits=None):
    """Deep LLM resume tailoring incorporating company intelligence, domain fit, and ATS alignment.
    Strictly truth-grounded to the Vault profile facts."""
    data = build(p, job, limits=limits)
    if not job or not job.get("company"):
        return data

    company_name = str(job.get("company", "")).strip()
    job_title = str(job.get("title", "")).strip()

    # 1. Fetch or use company research dossier
    if not company_research:
        try:
            from . import company_researcher
            company_research = company_researcher.research_company(
                company=company_name,
                job_title=job_title,
                job_desc=job.get("desc") or job.get("description") or "",
                job_url=job.get("url") or ""
            )
        except Exception:
            company_research = {}

    data["company_research"] = company_research or {}

    # 2. Re-prioritize projects based on company tech stack & domain keywords if available
    comp_tech = [t.lower() for t in (company_research.get("tech_stack") or [])]
    comp_domain = str(company_research.get("domain") or "").lower()

    if comp_tech or comp_domain:
        def _comp_project_score(pr):
            body = " ".join([pr.get("name", ""), " ".join(pr.get("bullets", [])), " ".join(pr.get("skills", []))]).lower()
            sc = sum(3 for ct in comp_tech if ct and ct in body)
            if any(w in body for w in comp_domain.split() if len(w) > 3):
                sc += 2
            return sc

        if data.get("projects"):
            data["projects"] = sorted(data["projects"], key=_comp_project_score, reverse=True)

    # 3. LLM-crafted company-aligned summary
    try:
        from . import llm_gateway
        facts = {
            "current_position": data.get("headline"),
            "skills": [s for _, vs in data.get("skills", []) for s in vs][:15],
            "experience": data.get("experience"),
            "projects": [{"name": x["name"], "skills": x.get("skills", []), "bullets": x["bullets"][:2]} for x in data.get("projects", [])]
        }

        c_mission = company_research.get("mission") or "software innovation"
        c_domain = company_research.get("domain") or "technology"
        c_angle = company_research.get("tailoring_angle") or "highlight engineering excellence and rapid adaptability"

        prompt = (
            f"You are an Elite Executive Career Coach & Technical Resume Strategist.\n"
            f"TARGET COMPANY: {company_name} (Domain: {c_domain})\n"
            f"MISSION: {c_mission}\n"
            f"RECOMMENDED TAILORING ANGLE: {c_angle}\n"
            f"TARGET ROLE: {job_title}\n\n"
            f"CANDIDATE VAULT FACTS (Use ONLY these facts; NEVER invent employers, tools, numbers, or experiences):\n"
            f"{facts}\n\n"
            f"Write a 2-3 sentence company-tailored resume summary (in third person, no 'I' or 'my') that positions the candidate as an ideal fit for {company_name} while strictly respecting the facts above.\n"
            f"Output ONLY the summary text, with no markdown quotes or extra commentary."
        )

        res = llm_gateway.gateway_generate(prompt, max_tokens=250)
        tailored_summary = (res.get("reply") or "").strip()
        tailored_summary = re.sub(r'["\n\r]+', ' ', tailored_summary).strip()

        if tailored_summary and len(tailored_summary) < 700 and claims_ok(tailored_summary, p):
            data["summary"] = tailored_summary
            data["_llm_tailored"] = True
            data["_llm_provider"] = res.get("provider", "gateway")
    except Exception:
        pass

    # 4. Attach application hook for cover letter / outreach
    data["tailored_pitch"] = company_research.get("application_hook") or f"Excited to apply my experience to {company_name}'s {job_title} role."
    return data


# ---------- rendering ----------
def _t(x): return html.escape(str(x or "").encode("cp1252", "replace").decode("cp1252"))      # built-in PDF fonts are Latin-1/cp1252 only
def _safe_url(u): return u if re.match(r"https?://", str(u or ""), re.I) else ""


def _story(d, fs):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, HRFlowable
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=fs, leading=fs * 1.28)
    st = {"name": ParagraphStyle("n", parent=base, fontName="Helvetica-Bold", fontSize=fs + 8, leading=fs + 11), "sub": ParagraphStyle("s", parent=base, textColor=colors.HexColor("#333333")),
          "h": ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=fs + 0.5, spaceBefore=fs * 0.7, spaceAfter=1, textColor=colors.HexColor("#111111")),
          "b": ParagraphStyle("bl", parent=base, leftIndent=11, bulletIndent=2, spaceAfter=0.6), "row": ParagraphStyle("r", parent=base, fontName="Helvetica-Bold", spaceBefore=2)}
    S = [Paragraph(_t(d["name"]) or "Resume", st["name"])]
    link = lambda lab, u: f'<link href="{html.escape(_safe_url(u))}" color="#1a4fa0">{_t(lab)}</link>' if _safe_url(u) else _t(lab)
    line = " | ".join([_t(c) for c in d["contact"]] + [link(l, u) for l, u in d["links"]])
    if line: S.append(Paragraph(line, st["sub"]))
    if d["headline"] and not d["summary"].startswith(d["headline"]): S.append(Paragraph(_t(d["headline"]), st["sub"]))

    def head(t): S.extend([Paragraph(t.upper(), st["h"]), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#888888"), spaceAfter=2)])
    def bul(items): S.extend(Paragraph(_t(b), st["b"], bulletText="\u2022") for b in items)
    if d["summary"]: head("Summary"); S.append(Paragraph(_t(d["summary"]), base))
    if d["skills"]: head("Skills"); S.extend(Paragraph(f"<b>{_t(l)}:</b> {_t(', '.join(vs))}", base) for l, vs in d["skills"])
    if d["experience"]:
        head("Experience")
        for e in d["experience"]:
            S.append(Paragraph(_t(" | ".join(x for x in (e["role"], e["company"], e["location"], e["period"]) if x)), st["row"])); bul(e["bullets"])
    if d["projects"]:
        head("Projects")
        for x in d["projects"]:
            S.append(Paragraph(_t(x["name"]) + (f" | {link(x['link'], x['link'])}" if _safe_url(x["link"]) else "") + (f" | {_t(x['period'])}" if x["period"] else ""), st["row"])); bul(x["bullets"])
    if d["education"]: head("Education"); S.extend(Paragraph(_t(e["text"]), base) for e in d["education"])
    if d["certifications"]: head("Certifications"); bul(d["certifications"])
    if d["achievements"]: head("Achievements"); bul(d["achievements"])
    if d["availability"]: head("Availability"); S.append(Paragraph(_t(d["availability"]), base))
    return S


def _trim(d):
    """Drop the least relevant thing (lists are already relevance-ordered). False when nothing is left to drop."""
    if d["achievements"]: d["achievements"].pop(); return True
    if len(d["certifications"]) > 2: d["certifications"].pop(); return True
    for key in ("projects", "experience"):
        for it in sorted(d[key], key=lambda x: -len(x["bullets"])):
            if len(it["bullets"]) > 2: it["bullets"].pop(); return True
    if len(d["projects"]) > 1: d["projects"].pop(); return True
    if d["certifications"]: d["certifications"].pop(); return True
    for key in ("projects", "experience"):
        for it in d[key]:
            if len(it["bullets"]) > 1: it["bullets"].pop(); return True
    return False


def render_pdf(data, path, sizes=(10, 9.5, 9, 8.5, 8)):
    """Writes a one-page PDF; returns {'font': pt, 'pages': n, 'dropped': bool}. The input dict is not modified."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    d, dropped = copy.deepcopy(data), False
    while True:
        for fs in sizes:
            buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=f"{d['name']} resume", author=d["name"])
            doc.build(_story(d, fs))
            if doc.page <= 1: break
        else:
            if _trim(d): dropped = True; continue
        break
    with open(path, "wb") as f: f.write(buf.getvalue())
    return {"font": fs, "pages": doc.page, "dropped": dropped}


def render_md(d):
    L = [f"# {d['name'] or 'Resume'}: tailored for {d['job']['title']} @ {d['job']['company']}" if d.get("job") else f"# {d['name']}", ""]
    L += [" | ".join(d["contact"] + [f"{l}: {u}" for l, u in d["links"]]), "", d["summary"], "", "## Skills"] + [f"- **{l}:** {', '.join(vs)}" for l, vs in d["skills"]]
    for e in d["experience"]: L += ["", f"### {' | '.join(x for x in (e['role'], e['company'], e['period']) if x)}"] + [f"- {b}" for b in e["bullets"]]
    if d["projects"]: L += ["", "## Projects"] + [f"- **{x['name']}**" + "".join(f"\n  - {b}" for b in x["bullets"]) for x in d["projects"]]
    for key, title in (("education", "Education"), ("certifications", "Certifications"), ("achievements", "Achievements")):
        if d[key]: L += ["", f"## {title}"] + [f"- {x['text'] if isinstance(x, dict) else x}" for x in d[key]]
    if d.get("job"): L += ["", f"**ATS coverage:** {d['ats']}%", "", f"**Do NOT claim (not in your vault):** {', '.join(d['missing']) or 'none'}"]
    if d.get("company_research"):
        cr = d["company_research"]
        L += [
            "",
            "## Company Intelligence Briefing",
            f"- **Domain:** {cr.get('domain', 'N/A')}",
            f"- **Mission:** {cr.get('mission', 'N/A')}",
            f"- **Core Tech Stack:** {', '.join(cr.get('tech_stack', [])) or 'N/A'}",
            f"- **Culture & Engineering Values:** {', '.join(cr.get('culture_values', [])) or 'N/A'}",
            f"- **Tailoring Strategy:** {cr.get('tailoring_angle', 'N/A')}",
            f"- **Tailored Pitch Hook:** {cr.get('application_hook', 'N/A')}"
        ]
    return "\n".join(L) + "\n"
