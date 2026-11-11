"""Autonomous Company Research Engine powered by LLM Gateway.

Researches company mission, business model, core tech stack, culture,
engineering values, and role-specific keywords to provide deep context
for tailored resume generation, cold outreach, and job applications.
"""
import datetime as dt, json, os, pathlib, re, urllib.parse, urllib.request
from typing import Dict, Any, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESEARCH_CACHE_DIR = ROOT / "private" / "company_research"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "company").lower()).strip("_")


def _get_cached_research(company: str) -> Optional[Dict[str, Any]]:
    """Return cached research if younger than 14 days."""
    path = RESEARCH_CACHE_DIR / f"{_slug(company)}.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ts = data.get("researched_at")
            if ts:
                age = (dt.datetime.now() - dt.datetime.fromisoformat(ts)).total_seconds()
                if age < 14 * 86400:
                    return data
        except Exception:
            pass
    return None


def _save_research(company: str, data: Dict[str, Any]) -> str:
    """Save company research dossier to private/company_research/."""
    RESEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = RESEARCH_CACHE_DIR / f"{_slug(company)}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def research_company(company: str, job_title: str = "", job_desc: str = "", job_url: str = "") -> Dict[str, Any]:
    """Research company domain, tech stack, mission, culture, and interview expectations."""
    company = str(company or "").strip()
    if not company:
        return {
            "company": "Target Company",
            "domain": "Technology & Software",
            "mission": "Deliver high-quality software solutions.",
            "tech_stack": ["Python", "JavaScript", "SQL", "Cloud", "Git"],
            "culture_values": ["Innovation", "Collaboration", "Engineering Excellence"],
            "tailoring_angle": "Emphasize clean code, scalable architecture, and quick adaptability.",
            "researched_at": dt.datetime.now().isoformat()
        }

    cached = _get_cached_research(company)
    if cached:
        return cached

    from . import llm_gateway

    clean_desc = (job_desc or "")[:1200]
    prompt = (
        f"You are a Senior Technical Recruiter & Company Intelligence Analyst.\n"
        f"TARGET COMPANY: {company}\n"
        f"ROLE: {job_title or 'Software Engineering'}\n"
        f"JOB CONTEXT: {clean_desc or 'Standard high-growth software engineering role'}\n\n"
        "Conduct a targeted company research brief to help an engineering candidate tailor their resume and application.\n"
        "Provide the response strictly as valid JSON with these exact keys:\n"
        "{\n"
        f'  "company": "{company}",\n'
        '  "domain": "<Primary industry or product focus, e.g. Fintech Payments, Cloud Infrastructure, AI Platform, E-commerce>",\n'
        '  "mission": "<1-2 sentences on what problem the company solves and their value proposition>",\n'
        '  "tech_stack": ["<Tech1>", "<Tech2>", "<Tech3>", "<Tech4>", "<Tech5>"],\n'
        '  "culture_values": ["<Core Engineering Value 1>", "<Value 2>", "<Value 3>"],\n'
        '  "tailoring_angle": "<Specific recommendation on what experiences, metrics, and architecture patterns to emphasize on the resume>",\n'
        '  "application_hook": "<1-2 sentences of why the candidate is excited to build at this company specifically>",\n'
        '  "high_priority_keywords": ["<Keyword1>", "<Keyword2>", "<Keyword3>", "<Keyword4>"]\n'
        "}\n"
        "Output ONLY the JSON object, with no markdown backticks or commentary."
    )

    llm_res = llm_gateway.gateway_generate(prompt, max_tokens=500)
    raw_text = (llm_res.get("reply") or "").strip()

    # Extract JSON safely
    research_data = None
    if "{" in raw_text and "}" in raw_text:
        try:
            json_str = raw_text[raw_text.find("{"):raw_text.rfind("}") + 1]
            research_data = json.loads(json_str)
        except Exception:
            research_data = None

    if not research_data or not isinstance(research_data, dict):
        # Heuristic fallback based on company name and description
        desc_lower = clean_desc.lower()
        domain = "Fintech & Payments" if any(w in desc_lower or w in company.lower() for w in ("pay", "finance", "bank", "credit", "fintech", "razorpay")) else (
            "Enterprise SaaS & Cloud" if any(w in desc_lower for w in ("saas", "cloud", "b2b", "enterprise", "aws")) else "Software & Technology Solutions"
        )
        techs = [s for s in ["Python", "FastAPI", "React", "PostgreSQL", "Docker", "AWS", "TypeScript", "REST APIs"] if s.lower() in desc_lower] or ["Python", "React", "SQL", "Cloud"]
        research_data = {
            "company": company,
            "domain": domain,
            "mission": f"Building scalable, mission-critical products at {company}.",
            "tech_stack": techs,
            "culture_values": ["High ownership", "Fast delivery", "Clean architecture"],
            "tailoring_angle": f"Highlight production system deployments, database design, and end-to-end API integrations for {company}.",
            "application_hook": f"Excited by {company}'s engineering impact in {domain} and eager to contribute reliable backend features.",
            "high_priority_keywords": techs[:5]
        }

    research_data["company"] = company
    research_data["researched_at"] = dt.datetime.now().isoformat()
    research_data["researched_by"] = llm_res.get("provider", "LLM Gateway")

    _save_research(company, research_data)
    return research_data
