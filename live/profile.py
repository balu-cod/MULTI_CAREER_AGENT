"""One profile schema. Public config lives in vault/user_profile_v1.json; contact details live in git-ignored private/profile.json."""
import json, os, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIVATE_KEYS = ("full_name", "contact_email", "contact_phone", "education", "linkedin")

DEFAULT_PROFILE = {
    "handle": "balu-cod",
    "current_position": "Software Developer Intern (3 months)",
    "target_roles": ["software engineer", "full stack", "backend", "python", "ai engineer", "developer", "intern"],
    "technical_skills": ["Python", "JavaScript", "HTML5", "CSS3", "Tailwind CSS", "SQL", "PostgreSQL", "Supabase", "FastAPI", "React", "Node.js", "PHP", "C++", "Java", "Docker", "Git", "GitHub Actions", "REST"],
    "skill_gaps": ["typescript", "kubernetes", "langgraph", "langchain", "mcp", "llm", "rag", "dsa", "mongodb", "aws"],
    "interests": ["ai agents", "llm", "fastapi", "automation"],
    "preferred_locations": ["remote", "hyderabad", "india"],
    "availability": "4 hrs/day Remote",
    "github": "https://github.com/balu-cod",
    "match_threshold": 60, "apply_threshold": 75, "max_age_days": 45, "max_apply_per_day": 10,
    "blocked_companies": [], "memory_keep": 90,
    "job_sources": {
        "greenhouse": ["cloudflare", "databricks", "sezzle", "enterpret", "karya", "cresta", "datacor", "eqtcorporation", "stripe", "vercel", "postman", "razorpay"],
        "lever": ["palantir", "mistral", "zoox", "plaid"],
        "ashby": ["langchain", "anyone-ai", "aiprise", "outmarket", "pinecone", "build-ai", "linear", "supabase"],
        "workable": [],
        "remotive": True,
        "arbeitnow": True,
        "hn_hiring": True,
        "remoteok": True,
        "jobicy": True,
        "himalayas": True,
        "pages": ["https://wellfound.com/jobs", "https://myinternships.in/internships-at/razorpay/software-development", "https://myinternships.in/internships-at/postman/software-development", "https://cloudsoftsol.com/blog/zoho-software-developer-internship-2026-java-python-dotnet/"]
    },
    "youtube": {"news": {"channels": ["@Fireship", "@aiexplained-official", "@mreflow"], "queries": [], "max_age_days": 4},
                "tech": {"channels": ["@freecodecamp", "@TechWorldwithNana", "@ArjanCodes", "@ThePrimeagen", "@CodeWithHarry"], "queries": [], "max_age_days": 14},
                "per_channel": 3, "limit": 12},
    "auto_apply": {"mode": "off", "limit": 5, "min_ats": 50},
    "experience": [
        {
            "role": "Software Developer Intern",
            "company": "Aditya Birla Garments Limited",
            "period": "Dec 2025 - Mar 2026",
            "location": "Bengaluru / Plant Operations",
            "bullets": [
                "Engineered and deployed Trims Information Management System (TIMS) and File Shelf Tracker using Python, PHP, SQL, and JavaScript",
                "Authored complete technical architecture manuals and reduced physical record retrieval time by 65%"
            ],
            "skills": ["Python", "SQL", "JavaScript", "HTML5", "Git"]
        }
    ],
    "projects": [
        {
            "name": "CAREER_AGENT_SYSTEM v6.5",
            "link": "https://github.com/balu-cod/career-agent-system",
            "period": "2026",
            "bullets": [
                "Autonomous 18-agent DAG pipeline scanning Greenhouse, Lever, Ashby, Remotive, Arbeitnow, and Hacker News",
                "Builds single-page ATS-tailored PDF resumes, SHA-256 verified Vault artifacts, and SMTP email digests"
            ],
            "skills": ["Python", "FastAPI", "SQL", "Docker", "Git"]
        },
        {
            "name": "Ai-Search Agentic Retrieval Engine",
            "link": "https://github.com/balu-cod/Ai-search",
            "period": "2026",
            "bullets": [
                "Multi-LLM synthesis and web search tool integrating Claude Code, OpenAI Codex, and Ollama local gateways",
                "Implemented structured JSON output validation and responsive web frontend"
            ],
            "skills": ["Python", "JavaScript", "React", "HTML5", "Tailwind CSS"]
        }
    ],
    "certifications": [
        {"name": "HackerRank Certified: Python (Basic)", "issuer": "HackerRank", "year": 2026},
        {"name": "Digital 101 (30-Hour Assessment)", "issuer": "FutureSkills Prime (NASSCOM & MeitY)", "year": 2026}
    ],
}
DEFAULT_ROADMAP = {"goal": "Land a software/AI role", "learning_roadmap": [
    {"phase": 1, "topic": "typescript", "title": "TypeScript for React and APIs", "duration_weeks": 3, "status": "in_progress"},
    {"phase": 2, "topic": "dsa", "title": "Data structures and algorithms", "duration_weeks": 6, "status": "planned"},
    {"phase": 3, "topic": "langgraph", "title": "Agent workflows with LangGraph", "duration_weeks": 3, "status": "planned"}]}


def split_private(profile):
    """Return (public, private) so private keys never reach the committed Vault."""
    pub = {k: v for k, v in profile.items() if k not in PRIVATE_KEYS}
    return pub, {k: profile[k] for k in PRIVATE_KEYS if k in profile}


def load_private():
    p = ROOT / "private" / "profile.json"
    if os.getenv("PROFILE_JSON") and not p.exists():     # CI: written from a repo secret, never committed
        return json.loads(os.environ["PROFILE_JSON"])
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def merged_profile(vault):
    """Public Vault config + private contact details + active database profile."""
    pub = vault.load_artifact("user_profile_v1.json") or {}
    priv = load_private()
    db_prof = {}
    try:
        from . import user_data_backend as udb
        db_prof = udb.get_candidate_profile() or {}
    except Exception:
        pass
    clean_db = {k: v for k, v in db_prof.items() if v is not None}
    res = {**pub, **priv}
    for k in ("full_name", "name", "email", "contact_email", "phone", "contact_phone", "location", "education", "bio"):
        if k in clean_db and clean_db[k]:
            res[k] = clean_db[k]
    if not res.get("technical_skills") and clean_db.get("technical_skills"):
        res["technical_skills"] = clean_db["technical_skills"]
    if not res.get("target_roles") and clean_db.get("target_roles"):
        res["target_roles"] = clean_db["target_roles"]
    return res


RESUME_SECTIONS = {"experience": list, "projects": list, "certifications": list, "achievements": list, "skill_groups": dict, "technical_skills": list}


def check_profile(profile):
    """Human-readable problems in the resume-related Vault fields (empty list = fine)."""
    out = []
    for k, t in RESUME_SECTIONS.items():
        if k in profile and not isinstance(profile[k], t): out.append(f"{k} must be a {t.__name__}")
    for k, need in (("experience", ("role", "company")), ("projects", ("name",))):
        for n, it in enumerate(profile.get(k) if isinstance(profile.get(k), list) else []):
            if not isinstance(it, dict): out.append(f"{k}[{n}] must be an object"); continue
            if not any(it.get(f) for f in need): out.append(f"{k}[{n}] needs {' or '.join(need)}")
            for f in ("bullets", "skills"):
                if f in it and not isinstance(it[f], list): out.append(f"{k}[{n}].{f} must be a list")
    return out
