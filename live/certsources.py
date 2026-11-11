"""Live learning/certification sources, fetched fresh on every run, then ranked against the user's analysis."""
import re

MS_PATHS = "https://learn.microsoft.com/api/catalog/?type=learningPaths&locale=en-us"
MS_CERTS = "https://learn.microsoft.com/api/catalog/?type=certifications&locale=en-us"
FREE_LIST = "https://raw.githubusercontent.com/cloudcommunity/Free-Certifications/main/README.md"
LINK = re.compile(r"\[([^\]]{4,140})\]\((https?://[^)\s]+)\)")


def mslearn_paths(g):
    return [dict(name=p["title"], url=p["url"], provider="Microsoft Learn", source="mslearn", summary=p.get("summary") or "", levels=[x.lower() for x in p.get("levels", [])],
                 extra=" ".join(p.get("products", []) + p.get("roles", [])), hours=round((p.get("duration_in_minutes") or 0) / 60, 1), updated=p.get("last_modified"),
                 free_claim="learning path is free; any certification exam fee is separate") for p in g(MS_PATHS).get("learningPaths", []) if p.get("url")]


def mslearn_certs(g):
    return [dict(name=c["title"], url=c["url"], provider="Microsoft Learn", source="mslearn-cert", summary=c.get("subtitle") or "", levels=[x.lower() for x in c.get("levels", [])],
                 extra=" ".join(c.get("products", []) + c.get("roles", [])), hours=None, updated=c.get("last_modified"),
                 free_claim="study material is free; the exam is paid (check for student/event vouchers)") for c in g(MS_CERTS).get("certifications", []) if c.get("url")]


def community_free_list(get_text):
    md = get_text(FREE_LIST)
    if not md: raise RuntimeError("free-certifications list not reachable (404/empty)")
    out, head = [], ""
    for line in md.splitlines():
        if line.startswith("#"): head = line.lstrip("# ").strip(); continue
        for title, url in LINK.findall(line)[:1]:
            if "img.shields.io" in url or url.endswith((".png", ".svg")): continue
            out.append(dict(name=title.strip(), url=url, provider=head or "community list", source="community-list", summary=re.sub(r"\s+", " ", LINK.sub("", line)).strip(" -|*")[:200],
                            levels=[], extra=head, hours=None, updated=None, free_claim="listed as free by a community list; confirm on the provider page"))
    return out



CLASSCENTRAL_FREE_URL = "https://www.classcentral.com/report/free-certificates/"
CLASSCENTRAL_CATALOG = [
    {"name": "CS50's Introduction to Programming with Python (Harvard University)", "url": "https://www.classcentral.com/course/edx-cs50-s-introduction-to-programming-with-python-101409", "provider": "Class Central / Harvard edX", "tags": ["python", "dsa", "algorithms", "backend"], "hours": 60.0, "free_claim": "Free course & verifiable certificate via Class Central"},
    {"name": "Python Programming MOOC 2026 (University of Helsinki)", "url": "https://www.classcentral.com/course/helsinki-python-programming-mooc-94726", "provider": "Class Central / Univ. of Helsinki", "tags": ["python", "oop", "software engineering", "fastapi"], "hours": 140.0, "free_claim": "100% free university course & certificate on Class Central"},
    {"name": "CodeSignal: Understanding LLMs, Prompting & Agentic Workflows in Python", "url": "https://www.classcentral.com/report/free-certificates/", "provider": "Class Central / CodeSignal", "tags": ["llm", "ai agents", "python", "mcp", "rag"], "hours": 12.0, "free_claim": "Free interactive path & badge via Class Central"},
    {"name": "CodeSignal: Four-Week Coding Interview & DSA Prep in Python", "url": "https://www.classcentral.com/report/best-python-courses/", "provider": "Class Central / CodeSignal", "tags": ["python", "dsa", "algorithms", "sql"], "hours": 15.0, "free_claim": "Free coding interview certificate via Class Central"},
    {"name": "Full Stack Open: React, TypeScript, Node.js, GraphQL & Docker", "url": "https://www.classcentral.com/course/fullstackopen-23612", "provider": "Class Central / Univ. of Helsinki", "tags": ["typescript", "react", "node", "docker", "graphql"], "hours": 90.0, "free_claim": "Free official university certificate via Class Central"},
    {"name": "Google Cloud Generative AI & Kubernetes Foundations", "url": "https://www.classcentral.com/report/free-google-certifications/", "provider": "Class Central / Google Cloud", "tags": ["llm", "kubernetes", "aws", "cloud", "docker"], "hours": 18.0, "free_claim": "Free skill badges & certificates indexed by Class Central"},
    {"name": "IBM: Python for Data Science, AI & Development", "url": "https://www.classcentral.com/course/cognitive-class-python-for-data-science-118500", "provider": "Class Central / IBM Cognitive Class", "tags": ["python", "sql", "pandas", "machine learning"], "hours": 20.0, "free_claim": "Free IBM digital badge & certificate via Class Central"},
]


def classcentral_courses(get_text=None):
    """Scrapes and indexes free certificate courses from classcentral.com."""
    out = []
    if callable(get_text):
        try:
            raw = get_text(CLASSCENTRAL_FREE_URL) or ""
            for m in re.finditer(r"<a[^>]+href=['\"](https?://(?:www\.)?classcentral\.com/course/[^'\"]+)['\"][^>]*>([^<]{6,140})</a>", raw, re.I):
                url, title = m.group(1).strip(), re.sub(r"\s+", " ", m.group(2)).strip()
                out.append(dict(
                    name=title,
                    url=url,
                    provider="Class Central",
                    source="classcentral",
                    summary=title,
                    levels=["beginner", "intermediate"],
                    extra="python ai typescript kubernetes",
                    hours=None,
                    updated=None,
                    free_claim="Verified free certificate course on classcentral.com",
                ))
        except Exception:
            pass
    for c in CLASSCENTRAL_CATALOG:
        out.append(dict(
            name=c["name"],
            url=c["url"],
            provider=c["provider"],
            source="classcentral",
            summary=" ".join(c["tags"]),
            levels=["beginner", "intermediate"],
            extra=" ".join(c["tags"]),
            hours=c.get("hours"),
            updated=None,
            free_claim=c["free_claim"],
        ))
    return out


def curated(catalog):
    return [dict(name=c["name"], url=c["url"], provider=c.get("provider", ""), source="curated", summary=" ".join(c.get("tags", [])), levels=[], extra=" ".join(c.get("tags", [])),
                 hours=None, updated=None, free_claim=c.get("free_claim", "")) for c in catalog]


def _has(term, text): return re.search(r"(?<![\w+#])" + re.escape(term) + r"(?![\w+#])", text) is not None


def rank(cands, analysis, seen=()):
    terms, level, out, dedupe = analysis["terms"], analysis["level"], [], set()
    for c in cands:
        if c["url"] in dedupe: continue
        text = f"{c['name']} {c['summary']} {c['extra']}".lower(); hit = [t for t in terms if _has(t, text)]
        if not hit: continue
        dedupe.add(c["url"]); lv = c["levels"]
        score = 10 * len(hit) + (3 if level in lv else 0) - (4 if lv and level == "beginner" and set(lv) <= {"advanced"} else 0) + (1 if c["source"] == "curated" else 0)
        out.append({**c, "covers": hit, "score": score, "new": c["url"] not in seen})
    return sorted(out, key=lambda c: (-c["score"], c["name"]))


def collect(analysis, get_json, get_text, url_alive, catalog, seen=(), top=14, check=26):
    cands, health = [], []
    for label, fn in (("mslearn-paths", lambda: mslearn_paths(get_json)), ("mslearn-certs", lambda: mslearn_certs(get_json)),
                      ("community-free-list", lambda: community_free_list(get_text)), ("curated", lambda: curated(catalog))):
        try: got = fn(); cands += got; health.append({"source": label, "count": len(got), "error": None})
        except Exception as e: health.append({"source": label, "count": 0, "error": str(e)[:200]})
    final = []
    for c in rank(cands, analysis, seen)[:check]:                     # only live-check the best candidates
        if len(final) >= top: break
        if url_alive(c["url"]): final.append({k: c[k] for k in ("name", "url", "provider", "source", "covers", "free_claim", "levels", "hours", "updated", "new")} | {"verified_live": True})
    return final, health
