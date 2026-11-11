"""Profile Intelligence Engine: LLM-powered skills, certifications, and drawback analysis.
Analyzes candidate background, detects concrete technical gaps, recommends improvements,
and fetches matching certifications, free courses, and study materials.
"""
import datetime as dt, json, os, pathlib
from .profile import ROOT, merged_profile
from . import user_data_backend as udb

POPULAR_CERTIFICATIONS_CATALOG = [
    {
        "id": "mslearn-azure-fundamentals",
        "title": "Microsoft Certified: Azure Fundamentals (AZ-900)",
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/credentials/certifications/azure-fundamentals/",
        "category": "Cloud & Infrastructure",
        "skills": ["Azure", "Cloud Architecture", "Cloud Security", "SaaS/PaaS/IaaS"],
        "cost": "100% Free Study Material (Exam vouchers available for students)",
        "addresses_gap": "Lacking cloud infrastructure & enterprise cloud hosting knowledge"
    },
    {
        "id": "harvard-cs50x",
        "title": "CS50x: Introduction to Computer Science & Algorithmic Problem Solving",
        "provider": "Harvard University & edX",
        "url": "https://cs50.harvard.edu/x/",
        "category": "Computer Science & Systems",
        "skills": ["C", "Python", "SQL", "Data Structures", "Algorithms", "Memory Management"],
        "cost": "100% Free Coursework & Free Harvard Certificate",
        "addresses_gap": "Data structures & foundational systems architecture"
    },
    {
        "id": "freecodecamp-fullstack",
        "title": "Full Stack Developer & TypeScript Certification",
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/",
        "category": "Web & Backend Development",
        "skills": ["TypeScript", "React", "Node.js", "Express", "REST APIs", "Modern JavaScript"],
        "cost": "100% Free Verifiable Digital Credential",
        "addresses_gap": "Need for strict typing with TypeScript in full-stack applications"
    },
    {
        "id": "kaggle-machine-learning",
        "title": "Kaggle & Google: Advanced Machine Learning & Deep Learning Competencies",
        "provider": "Kaggle & Google",
        "url": "https://www.kaggle.com/learn",
        "category": "AI & Machine Learning",
        "skills": ["Python", "TensorFlow", "Pandas", "Feature Engineering", "Neural Networks"],
        "cost": "100% Free Verifiable Completion Badges",
        "addresses_gap": "Deepening practical applied ML and data modeling"
    },
    {
        "id": "cisco-networking-security",
        "title": "Cybersecurity & Network Systems Architecture",
        "provider": "Cisco Networking Academy",
        "url": "https://skillsforall.com/",
        "category": "Networking & Security",
        "skills": ["TCP/IP", "Network Security", "Cryptography", "Threat Assessment"],
        "cost": "100% Free Digital Badges on Credly",
        "addresses_gap": "Production networking, secure sockets, and API defense"
    },
    {
        "id": "linux-foundation-devops",
        "title": "Introduction to Linux, Git & Containerized DevOps",
        "provider": "The Linux Foundation",
        "url": "https://training.linuxfoundation.org/",
        "category": "DevOps & Systems",
        "skills": ["Linux CLI", "Bash Scripting", "Docker", "Git Workflows", "CI/CD"],
        "cost": "100% Free Verified Open Source Course",
        "addresses_gap": "Container orchestration, Docker workflows, and Linux server management"
    }
]


def audit_profile_with_llm(vault, ask_llm_fn=None, log=print):
    """Deep technical profile audit: evaluates candidate skills, certifications, and critical drawbacks."""
    p = merged_profile(vault)
    cand_name = p.get("full_name") or "Candidate"
    skills = p.get("technical_skills") or ["Python", "FastAPI", "SQL", "React", "Docker", "Git"]
    roles = p.get("target_roles") or ["software engineer", "backend", "ai engineer", "intern"]
    education = p.get("education") or []
    
    summary = {
        "candidate": cand_name,
        "current_position": p.get("current_position") or "Software Developer Intern",
        "target_roles": roles,
        "technical_skills": skills,
        "education": education,
        "verified_projects": [
            "TIMS (Tailoring Inventory Management System) at Aditya Birla Garments Ltd (Python, FastAPI, SQL, Docker, cutting tracking latency by 42%)",
            "File Shelf Tracker (Python, SQLite, REST microservices)"
        ]
    }
    
    analysis = None
    if ask_llm_fn:
        prompt = (
            f"You are a Senior Principal Engineering Hiring Manager conducting an in-depth candidate diagnostic for {cand_name}.\n"
            f"CANDIDATE PROFILE:\n{json.dumps(summary, indent=2)}\n\n"
            f"Perform a strict, truthful evaluation and return a JSON object with exactly these keys:\n"
            f"1. 'strengths': list of 4 concrete production strengths based on their real projects (e.g. TIMS inventory, FastAPI REST, SQL relational schemas, Docker containerization).\n"
            f"2. 'verified_skills': list of current verified technical skills.\n"
            f"3. 'drawbacks': list of 4 critical drawbacks or vulnerabilities that could cause rejection at top tech firms (e.g. lacks TypeScript, needs distributed caching/Redis, needs Kubernetes/cloud orchestration, lacks formal DSA benchmark scores).\n"
            f"4. 'skill_gaps': list of missing technologies to learn.\n"
            f"5. 'recommended_certifications': list of recommended certifications to address drawbacks.\n"
            f"6. 'strategic_advice': 2-sentence executive directive on how to position themselves to recruiters."
        )
        try:
            raw = ask_llm_fn(prompt, max_tokens=700)
            if raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    analysis = json.loads(raw[start:end])
        except Exception as e:
            log(f"[Profile Intel] LLM audit note: {e}")

    if not analysis or not isinstance(analysis, dict) or "drawbacks" not in analysis:
        known_skills_lower = {s.lower() for s in skills}
        standard_gaps = [
            ("typescript", "TypeScript: enterprise frontend/full-stack roles require strict type safety"),
            ("kubernetes", "Kubernetes & Cloud Scaling: lacking production container orchestration experience"),
            ("redis", "Distributed In-Memory Caching (Redis): required for high-concurrency microservices"),
            ("system_design", "System Design & Distributed Data Modeling: needs formal high-throughput architecture proof"),
            ("dsa", "Data Structures & Algorithms: needs formal competitive/LeetCode problem-solving portfolio")
        ]
        detected_drawbacks = [desc for gap_key, desc in standard_gaps if gap_key not in known_skills_lower]
        detected_gaps = [gap_key for gap_key, _ in standard_gaps if gap_key not in known_skills_lower]
        
        analysis = {
            "strengths": [
                "Production Backend Delivery: Proven real-world experience building TIMS inventory system with Python and FastAPI at Aditya Birla Garments Ltd.",
                "Relational Data Engineering: Strong SQL, PostgreSQL, and schema design skills with transactional integrity.",
                "Containerization & Microservices: Dockerized backend deployments and clean RESTful API contracts.",
                "Full-Stack Coordination: Ability to bridge React interfaces with asynchronous FastAPI services."
            ],
            "verified_skills": skills,
            "drawbacks": detected_drawbacks[:4],
            "skill_gaps": detected_gaps[:5],
            "recommended_certifications": [
                "Microsoft Certified: Azure Fundamentals (AZ-900)",
                "freeCodeCamp Full Stack & TypeScript Certification",
                "Harvard CS50x Computer Science & Algorithms Certificate",
                "The Linux Foundation: Linux CLI, Git & Docker DevOps"
            ],
            "strategic_advice": (
                f"Double down on your production TIMS inventory management system and FastAPI backend accomplishments at Aditya Birla. "
                f"Close the TypeScript and Cloud Infrastructure gaps within 14 days using free verifiable certifications to pass enterprise resume screens."
            )
        }

    analysis["candidate"] = cand_name
    analysis["timestamp"] = dt.datetime.now(dt.timezone.utc).isoformat()

    try:
        vault.save_artifact("skill_roadmap_v1.json", analysis, "application/json", ["roadmap", "skills"], "LIVE_PIPELINE_AGENT", agent_name="LIVE_PIPELINE_AGENT")
    except Exception:
        out_f = ROOT / "vault" / "skill_roadmap_v1.json"
        out_f.parent.mkdir(parents=True, exist_ok=True)
        out_f.write_text(json.dumps(analysis, indent=2), "utf-8")

    udb.record_ledger_action(
        "PROFILE_ANALYSIS",
        "LLM_PROFILE_AUDIT",
        f"Evaluated candidate {cand_name}: identified {len(analysis.get('strengths', []))} strengths and {len(analysis.get('drawbacks', []))} critical drawbacks/gaps.",
        actor="PROFILE_INTEL_AGENT"
    )

    log(f"[Profile Intel] Completed profile audit for {cand_name}: {len(analysis.get('drawbacks', []))} drawbacks identified.")
    return analysis


def fetch_matching_improvements(vault, drawbacks=None, log=print):
    """Fetch matching certifications, learning tracks, and study materials that address the user's drawbacks."""
    roadmap = {}
    try:
        roadmap = vault.load_artifact("skill_roadmap_v1.json") or {}
    except Exception:
        pass
    gaps = drawbacks or roadmap.get("skill_gaps") or ["typescript", "kubernetes", "cloud", "algorithms"]
    gaps_lower = {str(g).lower() for g in gaps}

    matched_certs = []
    for c in POPULAR_CERTIFICATIONS_CATALOG:
        relevance = sum(1 for sk in c["skills"] if sk.lower() in gaps_lower or any(g in sk.lower() for g in gaps_lower))
        matched_certs.append({
            **c,
            "relevance_score": relevance + (2 if "Free" in c["cost"] else 0)
        })

    matched_certs.sort(key=lambda x: x["relevance_score"], reverse=True)

    result = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "targeted_drawbacks": gaps,
        "certifications": matched_certs,
        "free_courses_count": len([c for c in matched_certs if "100% Free" in c["cost"]]),
        "study_materials": [
            {"title": "FastAPI & Microservices Architecture Flashcards", "file": "/private/flashcards.md", "topic": "Backend"},
            {"title": "SQL Relational Indexing & Query Optimization Guide", "file": "/vault/evening_review_v1.json", "topic": "Databases"},
            {"title": "Docker Multi-stage Builds & Production Hardening", "file": "/private/tailored/*.md", "topic": "DevOps"}
        ]
    }

    udb.record_ledger_action(
        "RESOURCE_DISCOVERY",
        "FETCH_CERTIFICATIONS",
        f"Matched {len(matched_certs)} verified learning tracks addressing {len(gaps)} profile gaps.",
        actor="RESOURCE_FINDER_AGENT"
    )

    return result
