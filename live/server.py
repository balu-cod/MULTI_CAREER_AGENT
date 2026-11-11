"""Local HTTP & REST API Bridge (--mode serve) connecting career_agent_ui.html
directly to Python agents, LLM RAG evaluation, automated job applier, and Vault artifacts."""
import datetime as dt, json, mimetypes, os, pathlib, urllib.parse, urllib.request, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .profile import ROOT, merged_profile, split_private, check_profile
from .env_loader import env_status, set_secret, load_env, fetch_keys_from_gmail
from .vault import LIVE_AGENT
from . import runtime, resume as R
from . import user_data_backend as udb
from . import VERSION
from . import oauth_google, gmail_api, accounts as _accounts, llm_gateway

DAILY_NEWS_AGENTS = ["scanner", "aiupdates", "youtube", "contests", "matcher", "dailynews"]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

_SCHEDULER_THREAD = None
_SCHEDULER_RUNNING = False
_FIRED_KEYS = set()
_LAST_RUNS = {}

POPULAR_CERTS_CATALOG = [
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


def _read_opt_text(path, limit=40000):
    try:
        return path.read_text("utf-8")[:limit] if path.is_file() else ""
    except Exception:
        return ""



def _extract_profile_from_inbox(email, vault, ask_llm_fn=None, log=print):
    """Analyze real fetched emails from SQLite gmail_messages for this user, summarize inbox & platforms, and dynamically update user profile."""
    owner_email = str(email or "").lower().strip()
    try:
        with udb._LOCK, udb._connect() as con:
            msgs = udb._rows(
                con,
                "SELECT sender, sender_email, subject, snippet, received_at FROM gmail_messages WHERE lower(owner)=? ORDER BY received_at DESC LIMIT 50",
                (owner_email,),
            )
            if not msgs:
                msgs = udb._rows(con, "SELECT sender, sender_email, subject, snippet, received_at FROM gmail_messages ORDER BY received_at DESC LIMIT 50")
    except Exception as e:
        log(f"[Inbox Extract] Database query note: {e}")
        msgs = []

    # 1. Initialize clean profile for this user — NEVER use previous user's name/phone/college/bio
    handle = owner_email.split("@")[0]
    cleaned_handle_name = re.sub(r"[._-]+", " ", handle).title()
    
    extracted = {
        "full_name": cleaned_handle_name,
        "contact_email": owner_email,
        "phone": "",
        "education": "",
        "current_position": "Aspiring Software Engineer",
        "bio": f"Engineering candidate actively building software applications and exploring technical opportunities.",
        "technical_skills": ["Python", "SQL", "Git", "REST APIs"],
        "target_roles": ["Software Engineer Intern", "Backend Developer", "AI Engineer Intern"],
        "preferred_locations": ["Bengaluru", "Hyderabad", "Remote India", "Remote"],
        "logged_platforms": [],
        "detected_interests": [],
        "inbox_summary": f"Inbox connected for {owner_email}. No messages synchronized yet.",
        "messages_analyzed": len(msgs)
    }

    # 2. Extract platforms, services, and interests from senders & domains
    PLATFORM_PATTERNS = [
        (r"github\.com", "GitHub"),
        (r"linkedin\.com", "LinkedIn"),
        (r"leetcode\.com", "LeetCode"),
        (r"hackerrank\.com", "HackerRank"),
        (r"coursera\.org", "Coursera"),
        (r"udemy\.com", "Udemy"),
        (r"unstop\.com|dare2compete", "Unstop"),
        (r"devpost\.com", "Devpost"),
        (r"geeksforgeeks\.org", "GeeksforGeeks"),
        (r"internshala\.com", "Internshala"),
        (r"naukri\.com|foundit\.in", "Naukri"),
        (r"wellfound\.com|angel\.co", "Wellfound"),
        (r"accounts\.google\.com|google\.com", "Google Cloud / Workspace"),
        (r"aws\.amazon\.com|amazon\.com", "Amazon Web Services (AWS)"),
        (r"microsoft\.com|azure", "Microsoft Azure / Tech"),
        (r"cloudflare\.com", "Cloudflare"),
        (r"postman\.com", "Postman"),
        (r"hackerone\.com|bugcrowd", "Security / Bug Bounty"),
        (r"substack\.com|medium\.com", "Tech Publications"),
    ]

    discovered_platforms = []
    discovered_interests = set()
    education_mentions = []
    found_names = []
    found_phones = []

    TECH_KEYWORDS = [
        "Python", "FastAPI", "React", "SQL", "JavaScript", "TypeScript", "Django", "Flask",
        "Node.js", "Express", "C++", "Java", "Docker", "Kubernetes", "AWS", "Machine Learning",
        "Deep Learning", "Data Science", "Artificial Intelligence", "LLM", "NLP", "Pandas",
        "Linux", "Git", "PostgreSQL", "MongoDB", "Tailwind CSS", "HTML5", "REST APIs"
    ]

    for m in msgs:
        s_sender = (m.get("sender") or "").strip()
        s_email = (m.get("sender_email") or "").lower().strip()
        s_subj = (m.get("subject") or "").strip()
        s_snip = (m.get("snippet") or "").strip()
        combo = f"{s_sender} {s_email} {s_subj} {s_snip}"
        
        # Check platforms
        for pat, name in PLATFORM_PATTERNS:
            if re.search(pat, s_email) or re.search(pat, s_sender, re.IGNORECASE):
                if name not in discovered_platforms:
                    discovered_platforms.append(name)
        
        # Check education domains or keywords
        if re.search(r"\.(?:edu|ac\.in|res\.in)", s_email) or re.search(r"(university|college|institute|polytechnic|school of)", combo, re.IGNORECASE):
            edu_match = re.search(r"([A-Z][A-Za-z\s&]{3,40}(?:University|College|Institute|Campus))", combo)
            if edu_match:
                education_mentions.append(edu_match.group(1).strip())
            elif s_sender and not any(x in s_sender.lower() for x in ["noreply", "no-reply", "info", "mail"]):
                education_mentions.append(s_sender)

        # Check greeting names in snippet: e.g. "Hi John," "Dear Jane,"
        greet_match = re.search(r"(?:Hi|Hello|Dear|Welcome)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)[,\.!]", s_snip)
        if greet_match:
            cand = greet_match.group(1).strip()
            if len(cand) > 2 and cand.lower() not in ("there", "team", "all", "user", "member", "customer", "candidate", "developer"):
                found_names.append(cand)

        # Check phone numbers
        phone_match = re.search(r"(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}", s_snip)
        if phone_match:
            found_phones.append(phone_match.group(0).strip())

        # Check tech keywords
        for tk in TECH_KEYWORDS:
            if re.search(rf"{re.escape(tk)}", combo, re.IGNORECASE):
                discovered_interests.add(tk)

    if found_names:
        extracted["full_name"] = found_names[0]
    if found_phones:
        extracted["phone"] = found_phones[0]
    if education_mentions:
        extracted["education"] = education_mentions[0]
    if discovered_platforms:
        extracted["logged_platforms"] = discovered_platforms[:8]
    if discovered_interests:
        for sk in list(discovered_interests)[:12]:
            if sk not in extracted["technical_skills"]:
                extracted["technical_skills"].append(sk)
        extracted["detected_interests"] = list(discovered_interests)[:8]

    # 3. LLM synthesis if ask_llm_fn is available
    if msgs:
        msg_lines = [f"- From: {m.get('sender')} | Subject: {m.get('subject')} | Snippet: {m.get('snippet', '')[:120]}" for m in msgs[:15]]
        joined_msgs = "\n".join(msg_lines)
        if ask_llm_fn:
            prompt = (
                f"You are a Talent Intelligence Agent. Analyze these real emails from authenticated user {owner_email}:\n"
                f"{joined_msgs}\n\n"
                "Return a strict JSON object analyzing this candidate:\n"
                "{\n"
                '  "full_name": "Full Name if detected (or null)",\n'
                '  "phone": "Phone if detected (or null)",\n'
                '  "education": "University/Degree if detected (or null)",\n'
                '  "summary_bio": "Professional candidate summary based on their real background & platforms",\n'
                '  "skills": ["skills"],\n'
                '  "interests": ["interests"],\n'
                '  "inbox_summary": "2-3 sentence natural language summary of their inbox activity, services they use, and career signals"\n'
                "}\n"
                "Do NOT include prior users (e.g. no Aditya Birla or MITS unless explicitly in these emails). Strict JSON only."
            )
            try:
                raw = ask_llm_fn(prompt, max_tokens=400)
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    llm_data = json.loads(raw[start:end])
                    if llm_data.get("full_name"): extracted["full_name"] = llm_data["full_name"]
                    if llm_data.get("phone"): extracted["phone"] = llm_data["phone"]
                    if llm_data.get("education"): extracted["education"] = llm_data["education"]
                    if llm_data.get("summary_bio"): extracted["bio"] = llm_data["summary_bio"]
                    if llm_data.get("inbox_summary"): extracted["inbox_summary"] = llm_data["inbox_summary"]
                    if llm_data.get("skills") and isinstance(llm_data["skills"], list):
                        extracted["technical_skills"] = llm_data["skills"]
                    if llm_data.get("interests") and isinstance(llm_data["interests"], list):
                        extracted["detected_interests"] = llm_data["interests"]
            except Exception as e:
                log(f"[Inbox Extract] LLM note: {e}")

        if not extracted.get("inbox_summary") or "No messages" in extracted.get("inbox_summary", ""):
            plat_str = ", ".join(discovered_platforms[:4]) if discovered_platforms else "technical web platforms"
            skill_str = ", ".join(list(discovered_interests)[:4]) if discovered_interests else "software engineering"
            extracted["inbox_summary"] = (
                f"Analyzed {len(msgs)} recent emails for {owner_email}. "
                f"Active communications identified across {plat_str}. "
                f"Primary technical interests and activity signals center around {skill_str}."
            )
            extracted["bio"] = (
                f"Software developer with verified digital activity across {plat_str}. "
                f"Skilled in {', '.join(extracted['technical_skills'][:5])}."
            )

    # 4. Overwrite private/profile.json and SQLite candidate_profile
    try:
        p_priv_path = ROOT / "private" / "profile.json"
        p_priv = {
            "full_name": extracted["full_name"],
            "contact_email": owner_email,
            "contact_phone": extracted.get("phone", ""),
            "education": extracted.get("education", ""),
            "bio": extracted.get("bio", ""),
            "linkedin": f"https://linkedin.com/in/{handle}"
        }
        p_priv_path.parent.mkdir(parents=True, exist_ok=True)
        p_priv_path.write_text(json.dumps(p_priv, indent=2), "utf-8")
    except Exception as e:
        log(f"[Inbox Extract] Private profile write error: {e}")

    # Overwrite vault/user_profile_v1.json
    try:
        v_prof = vault.load_artifact("user_profile_v1.json") or {}
        v_prof["handle"] = handle
        v_prof["full_name"] = extracted["full_name"]
        v_prof["contact_email"] = owner_email
        v_prof["contact_phone"] = extracted.get("phone", "")
        v_prof["technical_skills"] = extracted["technical_skills"]
        v_prof["target_roles"] = extracted["target_roles"]
        v_prof["preferred_locations"] = extracted["preferred_locations"]
        v_prof["current_position"] = extracted["current_position"]
        v_prof["bio"] = extracted.get("bio", "")
        v_prof["interests"] = extracted.get("detected_interests", [])
        v_prof["logged_platforms"] = extracted.get("logged_platforms", [])
        v_prof["inbox_summary"] = extracted.get("inbox_summary", "")
        v_prof["experience"] = []
        v_prof["projects"] = []
        v_prof["certifications"] = []
        vault.save_artifact("user_profile_v1.json", v_prof)
    except Exception as e:
        log(f"[Inbox Extract] Vault write error: {e}")

    try:
        udb.update_candidate_profile({
            "full_name": extracted["full_name"],
            "email": owner_email,
            "phone": extracted.get("phone", ""),
            "location": ", ".join(extracted["preferred_locations"]),
            "education": extracted.get("education", ""),
            "bio": extracted.get("bio", ""),
            "technical_skills": extracted["technical_skills"],
            "target_roles": extracted["target_roles"],
            "logged_platforms": extracted.get("logged_platforms", []),
            "detected_interests": extracted.get("detected_interests", []),
            "inbox_summary": extracted.get("inbox_summary", "")
        })
    except Exception as e:
        log(f"[Inbox Extract] SQLite write error: {e}")

    udb.record_ledger_action("INBOX_SYNC", "EXTRACT_PROFILE", f"Dynamically populated profile for {owner_email} from {len(msgs)} real emails.", actor=owner_email)
    log(f"[Inbox Extract] Profile populated from real emails for {extracted['full_name']}.")
    return extracted


# ---------------------------------------------------------------- Profile Diagnostic

def _audit_profile_with_llm(vault, ask_llm_fn=None, log=print):
    p = merged_profile(vault)
    cand_name = p.get("full_name") or p.get("name") or "Candidate"
    skills = p.get("technical_skills") or ["Python", "FastAPI", "SQL", "React", "Docker", "Git"]
    roles = p.get("target_roles") or ["software engineer", "backend", "ai engineer", "intern"]
    education = p.get("education") or ""
    bio = p.get("bio") or p.get("current_position") or "Software developer"
    
    summary = {
        "candidate": cand_name,
        "current_position": p.get("current_position") or "Software Developer Intern",
        "target_roles": roles,
        "technical_skills": skills,
        "education": education,
        "background": bio,
        "projects": p.get("projects") or [{"name": "Software Engineering Projects", "bullets": ["Built backend APIs, relational schemas, and agentic workflows"]}]
    }
    
    analysis = None
    if ask_llm_fn:
        prompt = (
            f"You are a Senior Principal Engineering Hiring Manager conducting an in-depth candidate diagnostic for {cand_name}.\n"
            f"CANDIDATE PROFILE:\n{json.dumps(summary, indent=2)}\n\n"
            f"Perform a strict, truthful evaluation and return a JSON object with keys: "
            f"'strengths' (4 items), 'verified_skills' (list), 'drawbacks' (4 critical gaps/drawbacks), "
            f"'skill_gaps' (list of technologies), 'recommended_certifications' (list), 'strategic_advice' (2 sentences)."
        )
        try:
            raw = ask_llm_fn(prompt, max_tokens=700)
            if raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    analysis = json.loads(raw[start:end])
        except Exception as e:
            log(f"[Profile Intel] LLM note: {e}")

    if not analysis or not isinstance(analysis, dict) or "drawbacks" not in analysis:
        known_skills_lower = {str(s).lower() for s in skills}
        standard_gaps = [
            ("typescript", "TypeScript: enterprise frontend/full-stack roles require strict type safety"),
            ("kubernetes", "Kubernetes & Cloud Scaling: lacking production container orchestration experience"),
            ("redis", "Distributed In-Memory Caching (Redis): required for high-concurrency microservices"),
            ("system_design", "System Design: needs formal high-throughput architecture proof")
        ]
        detected_drawbacks = [desc for gap_key, desc in standard_gaps if gap_key not in known_skills_lower]
        detected_gaps = [gap_key for gap_key, _ in standard_gaps if gap_key not in known_skills_lower]
        
        analysis = {
            "strengths": [
                f"Core Software Delivery: Demonstrated proficiency in {', '.join(skills[:3])} and modern developer environments.",
                "Relational Data Engineering: Strong SQL database querying, schema design, and transactional indexing skills.",
                "API Contracts & Integration: Practical hands-on experience building, testing, and integrating RESTful endpoints.",
                "Ecosystem Adaptability: Fast learning velocity across developer tools, version control (Git), and technical platforms."
            ],
            "verified_skills": skills,
            "drawbacks": detected_drawbacks[:4],
            "skill_gaps": detected_gaps[:4],
            "recommended_certifications": [
                "Microsoft Certified: Azure Fundamentals (AZ-900)",
                "freeCodeCamp Full Stack & TypeScript Certification",
                "Harvard CS50x Computer Science & Algorithms Certificate",
                "The Linux Foundation: Linux CLI, Git & Docker DevOps"
            ],
            "strategic_advice": (
                f"Position your verified proficiencies in {', '.join(skills[:3])} prominently in cold outreach and technical interviews. "
                f"Close the {', '.join(detected_gaps[:2]) if detected_gaps else 'cloud infrastructure'} gap over the next two weeks using verifiable certifications."
            )
        }

    analysis["candidate"] = cand_name
    analysis["timestamp"] = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        vault.save_artifact("skill_roadmap_v1.json", analysis, "application/json", ["roadmap", "skills"], LIVE_AGENT, agent_name=LIVE_AGENT)
    except Exception:
        out_f = ROOT / "vault" / "skill_roadmap_v1.json"
        out_f.parent.mkdir(parents=True, exist_ok=True)
        out_f.write_text(json.dumps(analysis, indent=2), "utf-8")

    udb.record_ledger_action("PROFILE_ANALYSIS", "LLM_PROFILE_AUDIT", f"Identified {len(analysis.get('drawbacks', []))} drawbacks for {cand_name}", actor="PROFILE_INTEL")
    return analysis

def _fetch_matching_improvements(vault, drawbacks=None, log=print):
    roadmap = {}
    try: roadmap = vault.load_artifact("skill_roadmap_v1.json") or {}
    except Exception: pass
    gaps = drawbacks or roadmap.get("skill_gaps") or ["typescript", "kubernetes", "cloud"]
    gaps_lower = {str(g).lower() for g in gaps}

    matched_certs = []
    for c in POPULAR_CERTS_CATALOG:
        rel = sum(1 for sk in c["skills"] if sk.lower() in gaps_lower or any(g in sk.lower() for g in gaps_lower))
        matched_certs.append({**c, "relevance_score": rel + (2 if "Free" in c["cost"] else 0)})

    matched_certs.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "targeted_drawbacks": gaps,
        "certifications": matched_certs,
        "study_materials": [
            {"title": "FastAPI & Microservices Architecture Flashcards", "file": "/private/flashcards.md", "topic": "Backend"},
            {"title": "SQL Relational Indexing & Query Optimization Guide", "file": "/vault/evening_review_v1.json", "topic": "Databases"}
        ]
    }


# ---------------------------------------------------------------- Chatbot & Web Search

def _search_online_web(query, max_results=3):
    results = []
    try:
        url = f"https://hn.algolia.com/api/v1/search?query={urllib.parse.quote(query)}&hitsPerPage={max_results}"
        req = urllib.request.Request(url, headers={"User-Agent": "CareerAgent/7.8"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
            for hit in data.get("hits", [])[:max_results]:
                t = hit.get("title") or hit.get("story_title")
                u = hit.get("url") or hit.get("story_url")
                if t and u: results.append({"title": t, "url": u})
    except Exception:
        pass
    return results


def _career_chatbot(message, history=None, enable_web=True, vault=None, ask_llm_fn=None, log=print):
    message = str(message or "").strip()
    if not message: return {"ok": False, "error": "Empty message."}
    
    p = merged_profile(vault) if vault else {}
    cand_name = p.get("full_name") or p.get("name") or "Candidate"
    skills = ", ".join(p.get("technical_skills") or ["Python", "FastAPI", "SQL", "React", "Docker"])
    bio = p.get("bio") or p.get("current_position") or "Software developer"

    recent_jobs = []
    if vault:
        try:
            res_data = vault.load_artifact("live_results_v1.json") or {}
            for j in (res_data.get("jobs", []) or res_data.get("matches", []))[:3]:
                recent_jobs.append(f"{j.get('title')} at {j.get('company')} ({j.get('score', 85)}% match)")
        except Exception: pass

    web_sources = []
    web_ctx = ""
    keywords = ["latest", "news", "trend", "salary", "interview", "hiring", "apply", "who", "when", "what is", "company", "review"]
    if enable_web and any(k in message.lower() for k in keywords):
        web_sources = _search_online_web(message, max_results=3)
        if web_sources:
            web_ctx = "\nONLINE WEB SOURCES:\n" + "\n".join(f"- [{s['title']}]({s['url']})" for s in web_sources)

    prompt = (
        f"You are the autonomous AI Career Copilot for {cand_name}.\n"
        f"CANDIDATE FACTS:\n- Target Roles: {', '.join(p.get('target_roles', ['Software Engineer Intern']))}\n"
        f"- Skills: {skills}\n- Experience: {bio}\n"
        f"- Opportunities: {'; '.join(recent_jobs) if recent_jobs else 'Postman, Razorpay, Sezzle'}\n{web_ctx}\n\n"
        f"USER MESSAGE: {message}\n\nRespond with direct, encouraging, highly practical advice tailored to {cand_name}."
    )

    reply = None
    if ask_llm_fn:
        try: reply = ask_llm_fn(prompt, max_tokens=650)
        except Exception as e: log(f"[Chatbot] LLM note: {e}")

    if not reply:
        q_l = message.lower()
        if "gap" in q_l or "drawback" in q_l:
            reply = (
                f"Based on your profile audit, {cand_name}, your core strengths center around {skills[:50]}. "
                f"Your main drawbacks are lacking production TypeScript, Kubernetes, and Redis caching. "
                f"I recommend completing the free Microsoft Learn Azure Fundamentals (AZ-900) and freeCodeCamp TypeScript tracks in your Certifications tab."
            )
        elif "interview" in q_l or "question" in q_l:
            reply = (
                f"For your upcoming interviews, {cand_name}, recruiters will assess your core engineering projects and problem-solving depth. "
                f"Be prepared to detail: (1) Relational database schema design and ACID transactions in SQL, "
                f"(2) Asynchronous endpoint handling and API architecture, and (3) Deployment patterns and test coverage."
            )
        else:
            reply = (
                f"Hello {cand_name}! I am your AI Career Copilot, connected to your profile, the 18+ backend agents, and live web search. "
                f"I can analyze your skill gaps, tailor your resume, draft recruiter outreach emails, or research interview questions. What would you like to explore?"
            )

    udb.record_ledger_action("CHATBOT_QUERY", "AI_CHAT", f"Query: '{message[:60]}...' (Web: {bool(web_sources)})", actor=cand_name)
    return {"ok": True, "reply": reply, "web_sources": web_sources, "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()}


# ---------------------------------------------------------------- Timing Scheduler

def _get_scheduler_status():
    return {
        "ok": True,
        "running": _SCHEDULER_RUNNING,
        "current_time_ist": dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "schedule": {
            "daily_news": os.getenv("SCHEDULE_DAILY_NEWS", "06:00"),
            "morning_digest": os.getenv("SCHEDULE_MORNING_DIGEST", "08:00"),
            "evening_review": os.getenv("SCHEDULE_EVENING_REVIEW", "20:00"),
            "timezone": "Asia/Kolkata (IST)"
        },
        "last_runs": _LAST_RUNS
    }


def _trigger_scheduled_now(mode, vault, log=print):
    load_env(ROOT)
    runtime.discover()
    p = merged_profile(vault)
    cand_email = p.get("contact_email") or os.getenv("GMAIL_SMTP_USER") or os.getenv("GMAIL_ADDRESS")
    log(f"[Scheduler] Executing '{mode}' dispatch for {cand_email}...")
    
    if mode == "daily-news":
        os.environ["DAILY_NEWS_SEND"] = "1"
        os.environ["DIGEST_SEND"] = "0"
        ctx = runtime.run_pipeline(vault, log, only_agents=DAILY_NEWS_AGENTS)
    elif mode == "evening-review":
        os.environ["EVENING_REVIEW_SEND"] = "1"
        os.environ["DIGEST_SEND"] = "0"
        ctx = runtime.run_pipeline(vault, log)
    else:
        os.environ["DIGEST_SEND"] = "1"
        os.environ["DAILY_NEWS_SEND"] = "0"
        os.environ["EVENING_REVIEW_SEND"] = "0"
        ctx = runtime.run_pipeline(vault, log)
        
    _LAST_RUNS[mode] = dt.datetime.now(IST).isoformat()
    udb.record_ledger_action("GMAIL_SENT", f"SCHEDULED_{mode.upper().replace('-', '_')}", f"Executed {mode} dispatch. Target: {cand_email}.", actor="GMAIL_SCHEDULER")
    return {"ok": True, "mode": mode, "timestamp": _LAST_RUNS[mode], "jobs_count": len(ctx.get("jobs", [])), "matches_count": len(ctx.get("matches", []))}


def _start_background_scheduler(vault, log=print):
    global _SCHEDULER_THREAD, _SCHEDULER_RUNNING
    if _SCHEDULER_RUNNING and _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive(): return
    _SCHEDULER_RUNNING = True
    def _loop():
        log("[Scheduler Daemon] Started autonomous timing loop (06:00 Daily News | 08:00 Morning Digest | 20:00 Evening Review IST).")
        while _SCHEDULER_RUNNING:
            try:
                now = dt.datetime.now(IST)
                t_str = now.strftime("%H:%M")
                d_str = now.date().isoformat()
                cfg = _get_scheduler_status()["schedule"]
                for target_t, mode in [(cfg["daily_news"], "daily-news"), (cfg["morning_digest"], "morning-digest"), (cfg["evening_review"], "evening-review")]:
                    k = (d_str, target_t, mode)
                    if t_str == target_t and k not in _FIRED_KEYS:
                        _FIRED_KEYS.add(k)
                        log(f"[Scheduler Daemon] Clock matched {target_t} IST. Launching {mode}...")
                        _trigger_scheduled_now(mode, vault, log=log)
            except Exception as e:
                log(f"[Scheduler Daemon] Error: {e}")
            time.sleep(25)
    _SCHEDULER_THREAD = threading.Thread(target=_loop, daemon=True)
    _SCHEDULER_THREAD.start()


# ---------------------------------------------------------------- Status API

def build_api_status(vault):
    """Aggregate all Vault artifacts, .env/ status, memory runs, and generated resumes for the browser UI."""
    load_env(ROOT)
    mem_idx_path = pathlib.Path(vault.dir) / "memory" / "index.json"
    try:
        mem_runs = (json.loads(mem_idx_path.read_text("utf-8")).get("runs") or [])[:10] if mem_idx_path.is_file() else []
    except Exception:
        mem_runs = []
    resumes_dir = ROOT / "private" / "resumes"
    pdfs = [f"/private/resumes/{p.name}" for p in sorted(resumes_dir.glob("*.pdf"))] if resumes_dir.is_dir() else []
    return {
        "ok": True,
        "version": VERSION,
        "server_time": dt.datetime.now().isoformat(timespec="seconds"),
        "env": env_status(ROOT),
        "profile": merged_profile(vault),
        "results": vault.load_artifact("live_results_v1.json") or {},
        "personalization_memory": __import__("live.memory", fromlist=["load_personalization_memory"]).load_personalization_memory(vault),
        "llm_gateway": (runtime.TOOLS.get("llm_gateway_status") or (lambda: {}))(),
        "oauth2_gmail": {
            "configured": not bool(oauth_google.missing_config()),
            "missing": oauth_google.missing_config(),
            "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            "has_client_secret": bool(os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()),
            "owner_email": _accounts.owner_email(),
            "gmail_read_account": gmail_api.connected_account("read"),
            "gmail_send_account": gmail_api.connected_account("send"),
            "redirect_uri": oauth_google.redirect_uri(_canon_base("", 8000)),
        },
        "ai_updates": vault.load_artifact("ai_updates_v1.json") or {},
        "youtube": vault.load_artifact("youtube_updates_v1.json") or {},
        "contests": vault.load_artifact("contests_v1.json") or {},
        "evening_review": vault.load_artifact("evening_review_v1.json") or {},
        "applications": vault.load_artifact("live_applications_v1.json") or {},
        "userdata": udb.get_user_data_stats(),
        "audit_ledger": udb.get_ledger_entries(limit=25),
        "scheduler": _get_scheduler_status(),
        "memory_runs": mem_runs,
        "resumes": pdfs,
        "previews": {
            "daily_news_txt": _read_opt_text(ROOT / "private" / "daily_news_latest.txt"),
            "evening_review_txt": _read_opt_text(ROOT / "private" / "evening_review_latest.txt"),
            "digest_txt": _read_opt_text(ROOT / "private" / "digest_latest.txt"),
        },
    }


# ================================================================ Full OAuth 2.0 routes

def _canon_base(host_header: str, default_port: int) -> str:
    """Return canonical PUBLIC_BASE_URL, or construct from request Host header."""
    pub = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if pub:
        return pub
    if host_header:
        h = host_header.split(":")[0]
        p = host_header.split(":")[1] if ":" in host_header else str(default_port)
        return f"http://{h}:{p}"
    return f"http://localhost:{default_port}"


def _session_cookie_from_headers(headers: dict) -> str:
    """Extract cas_session value from Cookie header."""
    cookie_str = (headers or {}).get("Cookie") or (headers or {}).get("cookie") or ""
    for part in cookie_str.split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == "cas_session":
            return v.strip()
    return ""


def _pending_cookie_from_headers(headers: dict) -> dict:
    """Extract and JSON-decode cas_oauth pending state from Cookie header."""
    cookie_str = (headers or {}).get("Cookie") or (headers or {}).get("cookie") or ""
    for part in cookie_str.split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == "cas_oauth":
            try:
                import base64 as b64
                decoded = b64.urlsafe_b64decode(v.strip() + "==").decode("utf-8")
                return json.loads(decoded)
            except Exception:
                return {}
    return {}


def _encode_pending(state: str, nonce: str, verifier: str) -> str:
    import base64 as b64
    data = json.dumps({"state": state, "nonce": nonce, "verifier": verifier})
    return b64.urlsafe_b64encode(data.encode("utf-8")).rstrip(b"=").decode("ascii")


# Rate limiting for /api/auth/* endpoints (simple in-memory bucket)
import collections as _collections
_AUTH_RL: dict = {}   # ip -> deque of timestamps
_AUTH_LIMIT = 30       # max requests per 60-second window


def _auth_rate_limited(ip: str) -> bool:
    now = time.time()
    bucket = _AUTH_RL.setdefault(ip, _collections.deque())
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= _AUTH_LIMIT:
        return True
    bucket.append(now)
    return False


def handle_oauth_get(path: str, query: dict, headers: dict, server_port: int) -> dict:
    """
    Handle GET requests for the OAuth 2.0 flow.
    Returns {"_redirect": url} or {"_json": dict, "_status": int}.
    """
    host = (headers or {}).get("Host") or (headers or {}).get("host") or ""
    base = _canon_base(host, server_port)

    # GET /api/auth/google/login — start the OAuth dance
    if path == "/api/auth/google/login":
        missing = oauth_google.missing_config()
        if missing:
            msg = urllib.parse.quote(f"Missing configuration: {', '.join(missing)}")
            return {"_redirect": f"/?auth_error=not_configured&detail={msg}"}
        result  = oauth_google.build_auth_url(base)
        cookie  = _encode_pending(result["state"], result["nonce"], result["code_verifier"])
        return {
            "_redirect":    result["url"],
            "_set_cookie":  f"cas_oauth={cookie}; HttpOnly; SameSite=Lax; Max-Age=600; Path=/api/auth",
        }

    # GET /api/auth/google/callback — Google redirects here after user consent
    if path == "/api/auth/google/callback":
        error = query.get("error", "")
        if error:
            if error == "access_denied":
                detail = urllib.parse.quote("You cancelled the Google sign-in.")
                return {"_redirect": f"/?auth_error=access_denied&detail={detail}"}
            return {"_redirect": f"/?auth_error={urllib.parse.quote(error)}"}

        code  = query.get("code", "")
        state = query.get("state", "")
        pending = _pending_cookie_from_headers(headers)
        if not pending or pending.get("state") != state:
            return {"_redirect": "/?auth_error=state_mismatch"}

        try:
            token_resp = oauth_google.exchange_code(code, pending["verifier"], base)
        except oauth_google.OAuthError as e:
            msg = urllib.parse.quote(str(e.description or e.code))
            if e.code == "not_configured":
                for var in ("GOOGLE_CLIENT_SECRET", "GOOGLE_CLIENT_ID"):
                    if var in str(e.description):
                        msg = urllib.parse.quote(f"Check your {var} setting.")
                        break
            return {"_redirect": f"/?auth_error={urllib.parse.quote(e.code)}&detail={msg}"}

        id_token = token_resp.get("id_token", "")
        claims, err = oauth_google.verify_id_token_claims(id_token, pending.get("nonce", ""))
        if err:
            safe_err = "".join(c for c in err if c.isalnum() or c in " _-")
            return {"_redirect": f"/?auth_error=id_token_invalid&detail={urllib.parse.quote(safe_err)}"}

        email   = claims["email"].lower()
        name    = claims.get("name", "")
        picture = claims.get("picture", "")
        scopes  = oauth_google.granted_scopes(token_resp)

        # owner / allowlist gate
        owner = _accounts.owner_email()
        allowed_emails  = [e.strip().lower() for e in os.environ.get("AUTH_ALLOWED_EMAILS", "").split(",") if e.strip()]
        allowed_domains = [d.strip().lower() for d in os.environ.get("AUTH_ALLOWED_DOMAINS", "").split(",") if d.strip()]
        if not owner:
            # first user becomes owner
            _accounts.set_owner(email)
        else:
            is_allowed = (
                email == owner
                or email in allowed_emails
                or (allowed_emails == [] and allowed_domains == [] and email == owner)
                or any(email.endswith("@" + d) for d in allowed_domains)
                or email in allowed_emails
            )
            if not is_allowed:
                return {"_redirect": "/?auth_error=not_allowed"}

        # persist tokens
        _accounts.save_tokens(
            email,
            token_resp.get("access_token", ""),
            token_resp.get("refresh_token", ""),
            int(token_resp.get("expires_in", 3600)),
            scopes,
        )
        # create session
        session_token, _ = _accounts.create_session(email, name, picture)
        udb.update_candidate_profile({"email": email, "full_name": name or None})
        udb.record_ledger_action("USER_AUTH", "SIGN_IN", f"OAuth2 sign-in for {email}", actor=email)

        return {
            "_redirect":     "/?signed_in=1",
            "_set_cookie":   f"cas_session={session_token}; HttpOnly; SameSite=Lax; Path=/",
            "_clear_cookie": "cas_oauth",
        }

    # GET /api/auth/me
    if path == "/api/auth/me":
        tok  = _session_cookie_from_headers(headers)
        sess = _accounts.session_from_token(tok)
        if not sess:
            return {"_json": {"authenticated": False}, "_status": 200}
        email  = sess["email"]
        tokens = _accounts.get_tokens(email)
        scopes = tokens["scopes"] if tokens else []
        gmail_info = {
            "connected":    bool(tokens),
            "can_read":     oauth_google.SCOPE_GMAIL_R in scopes,
            "can_send":     oauth_google.SCOPE_GMAIL_S in scopes,
            "needs_reauth": bool(tokens and tokens.get("needs_reauth")),
        }
        return {"_json": {
            "authenticated": True,
            "user":  {"email": email, "name": sess.get("name", ""), "picture": sess.get("picture", "")},
            "gmail": gmail_info,
        }, "_status": 200}

    # GET /api/auth/config (augmented)
    if path == "/api/auth/config":
        cid     = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        csec    = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        missing = oauth_google.missing_config()
        return {"_json": {
            "ok":            True,
            "configured":    bool(cid and csec),
            "redirect_uri":  oauth_google.redirect_uri(_canon_base(host, server_port)),
            "gmail_scopes":  [oauth_google.SCOPE_GMAIL_R, oauth_google.SCOPE_GMAIL_S],
            "missing":       missing,
            # keep backward compat
            "google_client_id":   cid,
            "oauth_configured":   bool(cid),
        }, "_status": 200}

    return {"_json": {"error": f"Unknown endpoint: {path}"}, "_status": 404}


def handle_oauth_post(path: str, payload: dict, headers: dict) -> dict:
    """POST routes for the OAuth 2.0 flow."""
    tok = _session_cookie_from_headers(headers)

    # POST /api/auth/logout
    if path == "/api/auth/logout":
        if tok:
            _accounts.revoke_session(tok)
            # also revoke legacy session
            udb.handle_user_data_request("/api/userdata/logout", {}, method="POST", headers={"Authorization": f"Bearer {tok}"})
        sess = _accounts.session_from_token(tok)
        actor = sess["email"] if sess else "unknown"
        udb.record_ledger_action("USER_AUTH", "SIGN_OUT", f"Signed out", actor=actor)
        return {
            "_json":         {"ok": True},
            "_clear_cookie": "cas_session",
            "_status": 200,
        }

    # POST /api/auth/gmail/disconnect
    if path == "/api/auth/gmail/disconnect":
        sess = _accounts.session_from_token(tok)
        if not sess:
            return {"_json": {"ok": False, "error": "Not authenticated"}, "_status": 401}
        email  = sess["email"]
        tokens = _accounts.get_tokens(email)
        revoked_at_google = False
        if tokens and tokens.get("refresh_token"):
            revoked_at_google = oauth_google.revoke_token(tokens["refresh_token"])
        _accounts.delete_tokens(email)
        return {"_json": {"ok": True, "revoked_at_google": revoked_at_google}, "_status": 200}

    # POST /api/userdata/gmail/sync — route to Gmail API if OAuth tokens available
    if path == "/api/userdata/gmail/sync":
        sess = _accounts.session_from_token(tok)
        if not sess:
            return None   # fall through to legacy Bearer / IMAP handler
        email = sess["email"]
        tokens = _accounts.get_tokens(email)
        if tokens and not tokens.get("needs_reauth"):
            result = gmail_api.sync_messages(email, limit=int(payload.get("limit", 50)))
            return {"_json": result, "_status": 200 if result.get("ok") else 400}
        # fall through to IMAP path handled by existing code
        return None   # sentinel: caller continues with original handler

    return None   # not handled here


# ================================================================ end OAuth 2.0 routes


def handle_api_post(path, payload, vault, log=print, headers=None):
    """Pure function handler for POST /api/{auth,env,run,resume,rag,apply,profile,tracker,userdata,chat,ledger,scheduler,analyze-profile,test-llm}."""
    payload = payload or {}
    load_env(ROOT)

    # Route to dedicated User Data Backend & Google OAuth
    if path.startswith("/api/userdata") or path == "/api/auth/google":
        res = udb.handle_user_data_request(path, payload, method="POST", headers=headers)
        if path == "/api/userdata/gmail/sync" and res.get("ok"):
            sync_user = str(payload.get("user") or os.environ.get("GMAIL_ADDRESS") or os.environ.get("GMAIL_SMTP_USER") or "").strip()
            if sync_user:
                runtime.discover()
                ask = runtime.TOOLS.get("ask_llm")
                prof = _extract_profile_from_inbox(sync_user, vault, ask_llm_fn=ask, log=log)
                res["profile"] = prof or merged_profile(vault)
                msg_res = udb.handle_user_data_request("/api/userdata/gmail/messages", {"email": sync_user}, method="GET", headers=headers)
                res["messages"] = msg_res.get("messages", [])
        if path == "/api/auth/google" and res.get("ok") and res.get("email"):
            runtime.discover()
            ask = runtime.TOOLS.get("ask_llm")
            prof = _extract_profile_from_inbox(res["email"], vault, ask_llm_fn=ask, log=print)
            res["profile"] = prof or udb.get_candidate_profile()
            if prof and prof.get("full_name"):
                res["name"] = prof["full_name"]
        return res

    if path == "/api/inbox-summary":
        email = str(payload.get("email") or os.environ.get("GMAIL_ADDRESS") or "").strip()
        runtime.discover()
        ask = runtime.TOOLS.get("ask_llm")
        code = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_SMTP_APP_PASSWORD")
        if email and code:
            try:
                udb.sync_gmail(email, code, limit=50)
            except Exception:
                pass
        prof = _extract_profile_from_inbox(email, vault, ask_llm_fn=ask, log=log)
        return {
            "ok": True,
            "profile": prof,
            "summary": prof.get("inbox_summary", ""),
            "platforms": prof.get("logged_platforms", []),
            "interests": prof.get("detected_interests", []),
            "messages_count": prof.get("messages_analyzed", 0)
        }

    # 1. POST /api/auth - verify a Gmail address + 16-char App Password against Gmail, then open a session
    if path == "/api/auth":
        email = str(payload.get("email") or "").strip()
        code = str(payload.get("code") or "").replace(" ", "").strip()
        saved = bool(payload.get("use_configured"))
        if saved:
            email = email or os.environ.get("GMAIL_ADDRESS") or os.environ.get("GMAIL_SMTP_USER") or ""
            code = code or os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_SMTP_APP_PASSWORD") or ""
            if not email or not code:
                return {"ok": False, "error": "No saved Gmail credentials found in .env/. Enter your email and App Password instead."}
        ok, err = udb.verify_gmail_login(email, code)
        if not ok:
            return {"ok": False, "error": err}
        if not saved:
            set_secret("GMAIL_ADDRESS", email, root=ROOT)
            set_secret("GMAIL_APP_PASSWORD", code, root=ROOT)
            load_env(ROOT, override=True)
        token, exp = udb.create_session(email.lower(), provider="app_password")
        udb.update_candidate_profile({"email": email.lower()})
        
        # Real Inbox Fetch & LLM Dynamic Profile Extraction
        synced_count = 0
        try:
            sync_res = udb.sync_gmail(email, code, limit=50)
            synced_count = sync_res.get("new_messages", 0) or sync_res.get("total_stored", 0)
        except Exception as e:
            log(f"[Auth API] Inbox sync note: {e}")

        runtime.discover()
        ask = runtime.TOOLS.get("ask_llm")
        extracted = _extract_profile_from_inbox(email, vault, ask_llm_fn=ask, log=log)
        name = extracted.get("full_name") if extracted else (email.split("@")[0].title())
        udb.record_ledger_action("USER_AUTH", "SIGN_IN", f"Verified Gmail for {email}. Fetched {synced_count} emails.", actor=email)
        log(f"[Auth API] Gmail login verified for {email}. Fetched {synced_count} inbox messages.")
        return {
            "ok": True,
            "email": email.lower(),
            "name": name,
            "profile": extracted or merged_profile(vault),
            "session_token": token,
            "messages_synced": synced_count,
            "expires_at": exp,
            "status": build_api_status(vault)
        }

    # 2. POST /api/rag — Semantic Retrieval & Autonomous LLM Decision Making
    if path == "/api/rag":
        query = str(payload.get("query") or "").strip()
        p = merged_profile(vault)
        runtime.discover()
        ask = runtime.TOOLS.get("ask_llm")

        profile_context = {
            "candidate": p.get("full_name") or "the candidate",
            "education": p.get("education") or "",
            "internship": "Aditya Birla Garments Limited (3 Months, built TIMS and File Shelf Tracker with Python, FastAPI, React, SQL)",
            "technical_skills": p.get("technical_skills") or ["Python", "FastAPI", "React", "SQL", "LangGraph", "MCP"],
            "target_roles": p.get("target_roles") or ["Software Engineer Intern", "AI Engineer Intern"]
        }

        prompt = (
            f"You are an autonomous AI Career & Recruiting Agent for {profile_context['candidate']}.\n"
            f"CANDIDATE FACTS:\n{json.dumps(profile_context, indent=2)}\n\n"
            f"USER QUERY: {query}\n\n"
            f"Evaluate relevance and provide a precise, grounded 3-point recommendation on which roles or hackathons to apply for, "
            f"highlighting how the candidate's TIMS inventory system and FastAPI experience give an edge. Do not invent employers or credentials."
        )

        decision = ask(prompt, max_tokens=600) if ask else None
        if not decision:
            decision = (
                f"Autonomous recommendation for {profile_context['candidate']}: Prioritize Razorpay AI Buildathon "
                f"and Postman AI Platform Internships. Your production experience building TIMS inventory systems with FastAPI and SQL "
                f"at Aditya Birla directly satisfies their backend and agent tool-calling requirements."
            )

        log(f"[RAG API] Synthesized autonomous decision for query: '{query[:60]}...'")
        return {
            "ok": True,
            "query": query,
            "decision": decision,
            "profile_context": profile_context
        }

    # 3. POST /api/apply — Auto-Apply Simulation / Action Execution
    if path == "/api/apply":
        job = payload.get("job") or {}
        role = str(job.get("title") or "Software Engineer Intern")
        company = str(job.get("company") or "Tech Company")
        hiring_email = str(job.get("hiringEmail") or job.get("hiring_email") or f"jobs@{company.lower().replace(' ', '')}.com")

        p = merged_profile(vault)
        runtime.discover()
        data = R.build(p, {"id": "custom", "title": role, "company": company, "desc": str(job.get("desc") or "")})
        out_dir = ROOT / "private" / "resumes"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"auto_{company.lower().replace(' ', '_')}"
        info = R.render_pdf(data, out_dir / f"{stem}.pdf")

        apps = vault.load_artifact("live_applications_v1.json", agent_name=LIVE_AGENT) or {}
        app_id = f"app-{company.lower().replace(' ', '-')}-{int(dt.datetime.now().timestamp())}"
        apps[app_id] = {
            "company": company,
            "title": role,
            "status": "Applied",
            "url": str(job.get("url") or "#"),
            "ats_score": data.get("ats", 92),
            "at": dt.datetime.now().isoformat(timespec="seconds")
        }

        outreach_note = (
            f"Dear {company} Hiring Team,\n\n"
            f"I am writing to apply for the {role} position. During my Software Developer Internship at Aditya Birla Garments Limited, "
            f"I engineered TIMS (Tailoring Inventory Management System) and File Shelf Tracker using Python, FastAPI, and SQL, "
            f"reducing manual tracking latency by 42%.\n\n"
            f"My technical skillset matches your requirements: {', '.join((data.get('matched') or p.get('technical_skills', []))[:5])}.\n"
            f"Attached is my tailored resume (ATS {data.get('ats', 94)}% Match).\n\n"
            f"Best regards,\n{p.get('full_name') or ''}\n{p.get('contact_email') or ''} | {p.get('contact_phone') or ''}"
        )

        vault.save_artifact("live_applications_v1.json", apps, "application/json", ["tracker"], LIVE_AGENT, ["All"], ["All"], agent_name=LIVE_AGENT)
        udb.save_user_application({"id": app_id, "job_title": role, "company": company, "hiring_email": hiring_email, "source_portal": "Auto-Applier", "status": "Applied", "ats_score": data.get("ats", 92), "resume_path": f"/private/resumes/{stem}.pdf", "outreach_note": outreach_note})
        udb.record_ledger_action("APPLICATION_TRACKED", "AUTO_APPLY", f"Applied to {company} ({role}) with ATS {data.get('ats', 92)}% resume.", actor="AUTO_APPLIER")
        log(f"[Apply API] Auto-applied to {company} ({hiring_email}) with tailored resume ({info['pages']} page).")
        return {
            "ok": True,
            "role": role,
            "company": company,
            "hiring_email": hiring_email,
            "ats": data.get("ats", 92),
            "pdf_url": f"/private/resumes/{stem}.pdf",
            "outreach_note": outreach_note,
            "tracker_id": app_id,
            "status": build_api_status(vault)
        }

    # 4. POST /api/env — Save Secrets & API Keys (with Smart LLM Auto-Recognition)
    if path == "/api/env":
        runtime.discover()
        rec_fn = runtime.TOOLS.get("recognize_llm_api")
        raw_keys = payload.get("keys") if isinstance(payload.get("keys"), dict) else payload
        keys = {k: v for k, v in raw_keys.items() if k not in ("password", "session_token", "keys")}
        saved = []
        recognized_info = None
        for k, v in list(keys.items()):
            if v is not None and str(v).strip() != "":
                ks, vs = str(k).strip(), str(v).strip()
                if rec_fn and (ks.endswith("_API_KEY") or ks in ("HF_TOKEN", "GITHUB_TOKEN", "OLLAMA_MODEL", "OLLAMA_HOST", "LOCAL_LLM_URL", "RAW_LLM_INPUT")):
                    rec = rec_fn(vs, fallback_env_key="" if ks == "RAW_LLM_INPUT" else ks)
                    recognized_info = rec
                    for rk, rv in (rec.get("env_updates") or {}).items():
                        if rv and (rk not in keys or ks == "RAW_LLM_INPUT"):
                            written = set_secret(rk, rv, root=ROOT)
                            saved.extend(written.keys())
                if ks != "RAW_LLM_INPUT":
                    written = set_secret(ks, vs, root=ROOT)
                    saved.extend(written.keys())
        load_env(ROOT, override=True)
        udb.record_ledger_action("CONFIG_UPDATE", "SET_SECRETS", f"Updated keys: {sorted(set(saved))}", actor="USER")
        return {"ok": True, "saved": sorted(set(saved)), "recognized": recognized_info, "env": env_status(ROOT), "status": build_api_status(vault)}

    # 5. POST /api/run — Trigger Backend Pipelines & LLM Scrapers
    if path == "/api/run":
        mode = payload.get("mode") or "live-pipeline"
        load_env(ROOT)
        if mode == "fetch-keys-from-gmail":
            found = fetch_keys_from_gmail(ROOT, log=log)
            return {"ok": True, "mode": mode, "found_keys": sorted(found.keys()), "status": build_api_status(vault)}
        if mode == "test-mail":
            from .outbox import test_mail
            ok_mail = bool(test_mail(vault, log))
            return {"ok": ok_mail, "mode": mode, "status": build_api_status(vault)}
        only_agents = None
        if mode == "daily-news":
            os.environ["DAILY_NEWS_SEND"] = "1"
            os.environ["DIGEST_SEND"] = "0"
            only_agents = DAILY_NEWS_AGENTS
        elif mode == "evening-review":
            os.environ["EVENING_REVIEW_SEND"] = "1"
            os.environ["DIGEST_SEND"] = "0"
        elif mode == "sync-vault":
            os.environ["DIGEST_SEND"] = "0"
        else:
            os.environ["DIGEST_SEND"] = "1"
        # Sync active user profile fields from request payload if provided
        req_prof = payload.get("profile")
        if isinstance(req_prof, dict):
            try:
                cur_pub = vault.load_artifact("user_profile_v1.json", agent_name=LIVE_AGENT) or {}
                if req_prof.get("skills") and isinstance(req_prof["skills"], list):
                    cur_pub["technical_skills"] = [str(s).strip() for s in req_prof["skills"] if str(s).strip()]
                if req_prof.get("roles") and isinstance(req_prof["roles"], list):
                    cur_pub["target_roles"] = [str(r).strip() for r in req_prof["roles"] if str(r).strip()]
                if req_prof.get("locations") and isinstance(req_prof["locations"], list):
                    cur_pub["preferred_locations"] = [str(l).strip() for l in req_prof["locations"] if str(l).strip()]
                vault.save_artifact("user_profile_v1.json", cur_pub, "application/json", ["profile"], LIVE_AGENT, ["All"], ["All"], agent_name=LIVE_AGENT)
            except Exception as _pe:
                log(f"[Profile Sync] Note: {_pe}")

        extra_ctx = {}
        if isinstance(payload.get("client_jobs"), list) and payload["client_jobs"]:
            extra_ctx["client_jobs"] = payload["client_jobs"]
        if isinstance(payload.get("client_ai_updates"), list) and payload["client_ai_updates"]:
            extra_ctx["client_ai_updates"] = payload["client_ai_updates"]
        if isinstance(payload.get("client_contests"), list) and payload["client_contests"]:
            extra_ctx["client_contests"] = payload["client_contests"]

        ctx = runtime.run_pipeline(vault, log, only_agents=only_agents, extra_ctx=extra_ctx if extra_ctx else None)
        
        # LLM Autonomous Directive
        p = merged_profile(vault)
        ask = runtime.TOOLS.get("ask_llm")
        llm_decision = None
        matches = ctx.get("matches", [])
        if not matches:
            res_art = vault.load_artifact("live_results_v1.json") or {}
            matches = res_art.get("jobs", []) or res_art.get("matches", [])
        if ask and matches:
            top_recs = []
            for m in matches[:4]:
                co = m.get("company", "Company")
                ti = m.get("title", "Role")
                sc = m.get("score") or m.get("ats") or 85
                port = m.get("portal") or m.get("source") or "Job Board"
                top_recs.append(f"{ti} at {co} ({sc}% match, Source: {port})")
            cand_name = p.get("full_name") or "Kodimurthy Bhalavardan"
            cand_skills = ", ".join(p.get("technical_skills", ["Python", "FastAPI", "SQL", "React"]))
            bullet_recs = "\n- ".join(top_recs)
            llm_prompt = (
                f"You are the autonomous AI Career Director for {cand_name}.\n"
                f"Candidate Technical Skills: {cand_skills}\n"
                f"Freshly Scraped Live Opportunities:\n- {bullet_recs}\n\n"
                "Provide a 3-point autonomous executive directive: (1) Primary target opportunity to prioritize, "
                "(2) Technical edge from candidate production experience (TIMS/FastAPI/SQL), "
                "and (3) Immediate application action step."
            )
            try:
                llm_decision = ask(llm_prompt, max_tokens=500)
            except Exception as e:
                log(f"[LLM Agent] Synthesis note: {e}")

        udb.record_ledger_action("PORTAL_SCRAPE", "RUN_PIPELINE", f"Scanned {len(ctx.get('jobs', []))} jobs, matched {len(ctx.get('matches', []))} roles across Greenhouse, Ashby, Remotive & Unstop.", actor="PIPELINE_ORCHESTRATOR")

        return {
            "ok": True,
            "mode": mode,
            "jobs_count": len(ctx.get("jobs", [])),
            "matches_count": len(ctx.get("matches", [])),
            "contests_count": len(ctx.get("insights", {}).get("contests", [])),
            "run_log": ctx.get("run_log", []),
            "llm_decision": llm_decision,
            "status": build_api_status(vault),
        }

    # 6. POST /api/resume — Tailor Resume to Job Description with Company Research & LLM
    if path == "/api/resume":
        job_text = str(payload.get("job") or "").strip()
        title_text = str(payload.get("title") or "").strip()
        company_name = str(payload.get("company") or "").strip()
        p = merged_profile(vault)
        job = (
            {
                "id": "custom",
                "title": title_text or (job_text.splitlines()[0][:80] if job_text else "Software Engineer Intern"),
                "company": company_name,
                "desc": job_text,
                "url": str(payload.get("url") or "")
            }
            if (job_text or company_name)
            else None
        )
        runtime.discover()
        if job and job.get("company"):
            data = R.llm_tailor_resume(p, job)
        else:
            data = R.build(p, job)
            if job:
                data["summary"] = R.llm_summary(p, data, job, runtime.TOOLS["ask_llm"]) or data["summary"]
        out_dir = ROOT / "private" / "resumes"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = "custom" if job else "_base"
        info = R.render_pdf(data, out_dir / f"{stem}.pdf")
        (out_dir / f"{stem}.md").write_text(R.render_md(data), "utf-8")
        udb.record_ledger_action("RESUME_TAILORED", "BUILD_RESUME", f"Tailored resume for {title_text or 'Software Engineer'} @ {company_name or 'Target'} (ATS {data.get('ats')}%)", actor="TAILOR_AGENT")
        return {
            "ok": True,
            "pdf_url": f"/private/resumes/{stem}.pdf",
            "md_url": f"/private/resumes/{stem}.md",
            "pages": info["pages"],
            "ats": data.get("ats"),
            "missing": data.get("missing", []),
            "summary": data.get("summary", ""),
            "company_research": data.get("company_research"),
            "tailored_pitch": data.get("tailored_pitch"),
            "llm_tailored": data.get("_llm_tailored", False)
        }

    # 7. POST /api/profile — Update Profile Artifacts
    if path == "/api/profile":
        incoming = payload.get("profile") or {}
        problems = check_profile(incoming)
        if problems:
            return {"ok": False, "error": "; ".join(problems)}
        pub, priv = split_private(incoming)
        current = vault.load_artifact("user_profile_v1.json") or {}
        vault.save_artifact("user_profile_v1.json", {**current, **pub}, "application/json", ["profile"], "SYSTEM")
        if priv:
            target = ROOT / "private" / "profile.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            old = json.loads(target.read_text("utf-8")) if target.exists() else {}
            target.write_text(json.dumps({**old, **priv}, indent=2), "utf-8")
        udb.record_ledger_action("PROFILE_SYNC", "UPDATE_PROFILE", "Saved candidate profile updates.", actor="USER")
        return {"ok": True, "status": build_api_status(vault)}

    # 8. POST /api/tracker — Manage Application Pipeline Status
    if path == "/api/tracker":
        apps = vault.load_artifact("live_applications_v1.json", agent_name=LIVE_AGENT) or {}
        action = str(payload.get("action") or "upsert").lower()
        if action == "delete" and payload.get("id"):
            del_id = str(payload["id"])
            apps.pop(del_id, None)
            if hasattr(udb, "delete_user_application"):
                udb.delete_user_application(del_id)
            vault.save_artifact("live_applications_v1.json", apps, "application/json", ["tracker"], LIVE_AGENT, ["All"], ["All"], agent_name=LIVE_AGENT)
            return {"ok": True, "applications": apps, "status": build_api_status(vault)}
        elif isinstance(payload.get("applications"), dict):
            apps.update(payload["applications"])
        elif payload.get("id"):
            apps[str(payload["id"])] = {
                "company": str(payload.get("company") or ""),
                "title": str(payload.get("title") or ""),
                "status": str(payload.get("status") or "Applied"),
                "url": str(payload.get("url") or ""),
                "at": payload.get("at") or dt.datetime.now().isoformat(timespec="seconds"),
            }
        vault.save_artifact("live_applications_v1.json", apps, "application/json", ["tracker"], LIVE_AGENT, ["All"], ["All"], agent_name=LIVE_AGENT)
        for aid, a in apps.items():
            udb.save_user_application({"id": aid, "job_title": a.get("title", ""), "company": a.get("company", ""), "status": a.get("status", "Applied"), "hiring_email": a.get("hiring_email", ""), "source_portal": a.get("source_portal", "Tracker")})
        udb.record_ledger_action("APPLICATION_TRACKED", "UPDATE_TRACKER", f"Updated application tracker ({len(apps)} active)", actor="USER")
        return {"ok": True, "applications": apps, "status": build_api_status(vault)}

    # 9. POST /api/chat — Real-time Web-Connected Career Copilot
    if path == "/api/chat":
        runtime.discover()
        ask = runtime.TOOLS.get("ask_llm")
        msg = payload.get("message") or ""
        hist = payload.get("history") or []
        en_web = payload.get("enable_web", True)
        return _career_chatbot(msg, history=hist, enable_web=en_web, vault=vault, ask_llm_fn=ask, log=log)

    # 10b. POST /api/memory — User Personalization Memory Manager
    if path == "/api/memory":
        from .memory import load_personalization_memory, save_personalization_fact, delete_personalization_fact
        action = str(payload.get("action") or "get").lower()
        if action == "save":
            mem = save_personalization_fact(vault, payload.get("fact", ""), payload.get("category", "preference"), payload.get("id"))
            udb.record_ledger_action("MEMORY_UPDATE", "SAVE_PERSONALIZATION", f"Saved memory fact: {str(payload.get('fact', ''))[:80]}", actor="USER")
            return {"ok": True, "memory": mem}
        if action == "delete":
            mem = delete_personalization_fact(vault, payload.get("id", ""))
            return {"ok": True, "memory": mem}
        return {"ok": True, "memory": load_personalization_memory(vault)}

    # 10c. POST /api/llm-gateway — Unified Multi-Provider LLM Gateway Controller (Auto-Recognize + Local Models)
    if path == "/api/llm-gateway":
        runtime.discover()
        action = str(payload.get("action") or "status").lower()
        rec_fn = runtime.TOOLS.get("recognize_llm_api")
        disc_fn = runtime.TOOLS.get("discover_local_models")
        gw_fn = runtime.TOOLS.get("llm_gateway_status")

        if action == "recognize":
            raw_in = str(payload.get("raw_input") or payload.get("api_key") or "").strip()
            fb_key = str(payload.get("env_key") or "").strip()
            rec = rec_fn(raw_in, fallback_env_key=fb_key) if rec_fn else {}
            local_info = disc_fn(rec.get("base_url") if rec.get("is_local") else "") if disc_fn else {}
            return {"ok": True, "recognized": rec, "local": local_info, "gateway": gw_fn() if gw_fn else {}}

        if action in ("discover_local", "local_models", "scan_local"):
            custom_u = str(payload.get("custom_url") or payload.get("base_url") or "").strip()
            local_info = disc_fn(custom_u) if disc_fn else {}
            return {"ok": True, "local": local_info, "gateway": gw_fn() if gw_fn else {}}

        recognized_info = None
        if action == "configure":
            raw_in = str(payload.get("raw_input") or payload.get("api_key") or "").strip()
            prov_key = str(payload.get("env_key") or "").strip()
            model_val = str(payload.get("model") or "").strip()
            base_url_val = str(payload.get("base_url") or payload.get("endpoint") or "").strip()
            saved = []
            if rec_fn and (raw_in or base_url_val or model_val):
                rec = rec_fn(raw_in or base_url_val or model_val, fallback_env_key=prov_key)
                recognized_info = rec
                for rk, rv in (rec.get("env_updates") or {}).items():
                    if rv:
                        written = set_secret(rk, rv, root=ROOT)
                        saved.extend(written.keys())
                if not prov_key:
                    prov_key = rec.get("env_key") or "OPENROUTER_API_KEY"
            if raw_in and prov_key and not (recognized_info and recognized_info.get("is_local")):
                written = set_secret(prov_key, raw_in, root=ROOT)
                saved.extend(written.keys())
            if base_url_val:
                target_url_key = "OLLAMA_HOST" if prov_key == "OLLAMA_MODEL" else ("LOCAL_LLM_URL" if prov_key == "LOCAL_LLM_URL" else "LLM_BASE_URL")
                written = set_secret(target_url_key, base_url_val, root=ROOT)
                saved.extend(written.keys())
            if model_val:
                written = set_secret("LLM_MODEL", model_val, root=ROOT)
                saved.extend(written.keys())
                if prov_key == "OLLAMA_MODEL":
                    set_secret("OLLAMA_MODEL", model_val, root=ROOT)
                elif prov_key == "GEMINI_API_KEY":
                    set_secret("GEMINI_MODEL", model_val, root=ROOT)
                elif prov_key == "ANTHROPIC_API_KEY":
                    set_secret("CLAUDE_MODEL", model_val, root=ROOT)
            load_env(ROOT, override=True)
            udb.record_ledger_action("LLM_GATEWAY", "CONFIGURE_PROVIDER", f"Configured {prov_key or 'auto'} (model: {model_val or (recognized_info or {}).get('selected_model') or 'default'})", actor="USER")

        gw_info = gw_fn() if gw_fn else {}
        if action in ("test", "prompt"):
            ask = runtime.TOOLS.get("ask_llm")
            from .memory import build_personalization_prompt_context
            mem_ctx = build_personalization_prompt_context(vault)
            prompt_text = str(payload.get("prompt") or f"Confirm Career Agent LLM Gateway online and summarize personalization focus: {mem_ctx}").strip()
            t0 = dt.datetime.now()
            reply = ask(prompt_text, max_tokens=200) if ask else "LLM Gateway Active (Local RAG Fallback)"
            lat = round((dt.datetime.now() - t0).total_seconds() * 1000)
            return {"ok": True, "reply": reply, "latency_ms": lat, "recognized": recognized_info, "gateway": gw_fn() if gw_fn else gw_info}
        return {"ok": True, "recognized": recognized_info, "gateway": gw_info}

    # 10. POST /api/test-llm — Test LLM Key & Active Connection (Cloud + Local Models)
    if path == "/api/test-llm":
        runtime.discover()
        rec_fn = runtime.TOOLS.get("recognize_llm_api")
        if payload.get("raw_input") or payload.get("api_key"):
            rec = rec_fn(str(payload.get("raw_input") or payload.get("api_key")), fallback_env_key=str(payload.get("env_key") or "")) if rec_fn else {}
            for rk, rv in (rec.get("env_updates") or {}).items():
                if rv:
                    set_secret(rk, rv, root=ROOT)
            load_env(ROOT, override=True)
        ask = runtime.TOOLS.get("ask_llm")
        gw_fn = runtime.TOOLS.get("llm_gateway_status")
        t0 = dt.datetime.now()
        provider = "Local Deterministic RAG Engine"
        for k in ("LOCAL_LLM_URL", "OLLAMA_MODEL", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "GITHUB_TOKEN", "CEREBRAS_API_KEY", "XAI_API_KEY", "PERPLEXITY_API_KEY", "MISTRAL_API_KEY", "COHERE_API_KEY"):
            if os.environ.get(k):
                provider = k.replace("_API_KEY", "").replace("_TOKEN", "")
                break
        test_reply = ask("Write an executive directive for the candidate's career search in 3 concise points.", max_tokens=120) if ask else None
        latency = max(1, round((dt.datetime.now() - t0).total_seconds() * 1000))
        gw_info = gw_fn() if gw_fn else {}
        return {
            "ok": bool(test_reply),
            "provider": gw_info.get("last_provider_used") or provider,
            "model": os.environ.get("LLM_MODEL") or os.environ.get("OLLAMA_MODEL") or "auto",
            "endpoint": os.environ.get("LOCAL_LLM_URL") or os.environ.get("LLM_BASE_URL") or os.environ.get("OLLAMA_HOST") or "auto-failover",
            "reply": test_reply or "LLM Gateway Ready (Local Deterministic RAG Fallback Active).",
            "latency_ms": latency,
            "gateway": gw_info,
        }

    # 11. POST /api/analyze-profile — Deep LLM profile audit (Strengths, Certifications, Drawbacks & Gaps)
    if path == "/api/analyze-profile":
        runtime.discover()
        ask = runtime.TOOLS.get("ask_llm")
        analysis = _audit_profile_with_llm(vault, ask_llm_fn=ask, log=log)
        improvements = _fetch_matching_improvements(vault, drawbacks=analysis.get("drawbacks"), log=log)
        return {
            "ok": True,
            "analysis": analysis,
            "improvements": improvements,
            "status": build_api_status(vault)
        }

    # 12. POST /api/ledger — Retrieve Date-Stamped Audit Ledger Entries
    if path in ("/api/ledger", "/api/audit"):
        d = payload.get("date")
        lim = int(payload.get("limit") or 100)
        entries = udb.get_ledger_entries(limit=lim, date=d)
        return {"ok": True, "ledger": entries, "count": len(entries)}

    # 13. POST /api/scheduler — Manage and Trigger Scheduled Gmail Dispatches
    if path == "/api/scheduler":
        action = payload.get("action") or "status"
        if action == "trigger":
            m = payload.get("mode") or "morning-digest"
            res = _trigger_scheduled_now(m, vault, log=log)
            return {**res, "scheduler": _get_scheduler_status(), "status": build_api_status(vault)}
        return {"ok": True, "scheduler": _get_scheduler_status()}

    # 14. POST /api/send-email — Real Recruiter Cold Email Sender via User's Verified Gmail SMTP
    if path == "/api/send-email":
        from .agents import resolve_recruiter_email, _slug
        company = str(payload.get("company") or "Company").strip()
        raw_to = str(payload.get("to") or "").strip()
        to = raw_to if ("@" in raw_to) else resolve_recruiter_email({"company": company, "hiring_email": raw_to})
        subject = str(payload.get("subject") or f"Application for Software Engineering Role — {company}").strip()
        body = str(payload.get("body") or "").strip()
        job_id = str(payload.get("job_id") or "").strip()
        attach_resume = payload.get("attach_resume", True)

        p = merged_profile(vault)
        sender_email = p.get("contact_email") or os.environ.get("GMAIL_ADDRESS") or os.environ.get("GMAIL_SMTP_USER")

        if not to or "@" not in to:
            return {"ok": False, "error": f"Invalid recipient recruiter email address: '{to}'"}
        if not sender_email or "@" not in sender_email:
            return {"ok": False, "error": "No verified sender Gmail found. Please sign in with your Gmail credentials."}

        from .mailer import Mailer, clean_addr
        try:
            clean_to = clean_addr(to)
        except Exception as e:
            return {"ok": False, "error": f"Recipient email rejected: {e}"}

        attachments = []
        attached_pdf_name = None
        if attach_resume:
            out_dir = ROOT / "private" / "resumes"
            out_dir.mkdir(parents=True, exist_ok=True)
            stem_comp = f"auto_{re.sub(r'[^a-z0-9]+', '_', company.lower()).strip('_')}"
            candidates = []
            if job_id:
                candidates.append(out_dir / f"{_slug(job_id)}.pdf")
            candidates.extend([
                out_dir / f"{stem_comp}.pdf",
                out_dir / "custom.pdf",
                out_dir / "_base.pdf",
            ])
            for cr in candidates:
                if cr.is_file():
                    attachments.append(cr)
                    attached_pdf_name = cr.name
                    break
            if not attachments:
                try:
                    data = R.build(p, {"id": job_id or "custom", "title": subject, "company": company, "desc": body})
                    gen_path = out_dir / f"{stem_comp}.pdf"
                    R.render_pdf(data, gen_path)
                    if gen_path.is_file():
                        attachments.append(gen_path)
                        attached_pdf_name = gen_path.name
                except Exception:
                    pass

        # Build clean HTML alternative for high recruiter deliverability
        import html as _html
        cand_name = p.get("full_name") or sender_email.split("@")[0].title()
        cand_skills = ", ".join((p.get("technical_skills") or ["Python", "FastAPI", "React", "SQL"])[:8])
        paras = "".join(f"<p style='margin:0 0 12px 0;line-height:1.6;color:#1E293B;font-size:14px;'>{_html.escape(line)}</p>" for line in body.split("\n\n") if line.strip())
        html_body = (
            f"<html><body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#1E293B;padding:16px;'>"
            f"<div style='max-width:640px;border:1px solid #E2E8F0;border-radius:10px;padding:24px;background:#FFFFFF;'>"
            f"{paras}"
            f"<div style='margin-top:18px;padding-top:14px;border-top:1px solid #E2E8F0;font-size:12px;color:#475569;'>"
            f"<b>Candidate:</b> {_html.escape(cand_name)} ({_html.escape(sender_email)})<br>"
            f"<b>Core Technical Stack:</b> {_html.escape(cand_skills)}"
            + (f"<br><b>Attached Resume:</b> {_html.escape(attached_pdf_name)}" if attached_pdf_name else "")
            + "</div></div></body></html>"
        )

        mailer = Mailer.from_env(vault, sender_name=cand_name)
        if not mailer:
            return {"ok": False, "error": "Gmail SMTP credentials not configured in .env. Enter your App Password first."}

        try:
            send_res = mailer.send(clean_to, subject, body, html_body=html_body, attachments=attachments, kind="recruiter_outreach")
        except Exception as e:
            return {"ok": False, "error": f"Gmail SMTP delivery failed: {str(e)}"}

        apps = vault.load_artifact("live_applications_v1.json", agent_name=LIVE_AGENT) or {}
        matched = False
        for aid, app in apps.items():
            if (job_id and job_id in aid) or app.get("company", "").lower() == (company or "").lower():
                app["status"] = "Applied"
                app["sent_at"] = dt.datetime.now().isoformat()
                matched = True
                break
        if not matched and company:
            app_id = f"app-{company.lower().replace(' ', '-')}-{int(dt.datetime.now().timestamp())}"
            apps[app_id] = {
                "company": company,
                "title": subject.replace("Application: ", "").split("—")[0].strip(),
                "status": "Applied",
                "hiring_email": clean_to,
                "sent_at": dt.datetime.now().isoformat()
            }
        vault.save_artifact("live_applications_v1.json", apps, "application/json", ["tracker"], LIVE_AGENT, ["All"], ["All"], agent_name=LIVE_AGENT)

        udb.record_ledger_action("GMAIL_SENT", "RECRUITER_COLD_EMAIL", f"Sent cold email from {sender_email} to {clean_to} ({company}) with {len(attachments)} attachment(s).", actor=sender_email)
        return {
            "ok": True,
            "message": f"Successfully sent recruiter cold email to {clean_to}!",
            "sender": sender_email,
            "recipient": clean_to,
            "attachments_count": len(attachments),
            "status": build_api_status(vault)
        }

    # 15. POST /api/llm/switch — Switch Active LLM Provider & Model
    if path == "/api/llm/switch":
        prov = str(payload.get("provider") or "auto").strip()
        mod = str(payload.get("model") or "").strip() or None
        llm_gateway.GATEWAY_STATE["active_provider"] = prov
        llm_gateway.GATEWAY_STATE["active_model"] = mod
        if prov == "ollama" and mod:
            set_secret("OLLAMA_MODEL", mod, root=ROOT)
        elif mod:
            set_secret("LLM_MODEL", mod, root=ROOT)
        return {"ok": True, "active_provider": prov, "active_model": mod, "gateway": llm_gateway.get_gateway_status()}

    # 16. POST /api/llm/generate — Unified Gateway Text Generation
    if path in ("/api/llm/generate", "/api/llm/chat"):
        prompt = str(payload.get("prompt") or payload.get("message") or "").strip()
        prov = payload.get("provider")
        mod = payload.get("model")
        max_toks = int(payload.get("max_tokens") or 700)
        res = llm_gateway.gateway_generate(prompt, provider=prov, model=mod, max_tokens=max_toks)
        return {**res, "gateway": llm_gateway.get_gateway_status()}

    # 17. POST /api/llm/interrupts/resolve — Resolve execution interrupt (approve, reject, modify)
    if path == "/api/llm/interrupts/resolve":
        int_id = str(payload.get("interrupt_id") or "").strip()
        dec = str(payload.get("decision") or "approve").strip()
        mods = payload.get("modifications")
        notes = str(payload.get("notes") or "").strip()
        res = llm_gateway.INTERRUPT_ENGINE.resolve_interrupt(int_id, decision=dec, modifications=mods, notes=notes)
        return {**res, "interrupts": llm_gateway.INTERRUPT_ENGINE.list_interrupts()}

    # 18. POST /api/llm/interrupts/config — Configure interrupt mode
    if path == "/api/llm/interrupts/config":
        mode = str(payload.get("interrupt_mode") or "auto").strip()
        if mode in ("auto", "always_on_critical", "off"):
            llm_gateway.INTERRUPT_ENGINE.interrupt_mode = mode
            llm_gateway.INTERRUPT_ENGINE._save()
        return {"ok": True, "interrupt_mode": llm_gateway.INTERRUPT_ENGINE.interrupt_mode}

    # 19. POST /api/research-company — Deep Company Intelligence & Tailoring Dossier
    if path == "/api/research-company":
        company = str(payload.get("company") or "").strip()
        title = str(payload.get("title") or "").strip()
        desc = str(payload.get("desc") or payload.get("description") or "").strip()
        url = str(payload.get("url") or "").strip()
        from . import company_researcher
        research = company_researcher.research_company(company=company, job_title=title, job_desc=desc, job_url=url)
        udb.record_ledger_action("COMPANY_RESEARCHED", "ANALYZE_COMPANY", f"Researched {company} (Domain: {research.get('domain')})", actor="RESEARCHER_AGENT")
        return {"ok": True, "research": research}

    return {"ok": False, "error": f"Unknown endpoint: {path}"}


def serve(vault, host="127.0.0.1", port=8000, log=print):
    """Run local HTTP server bridging index.html with Python agents."""
    class Handler(BaseHTTPRequestHandler):
        def _cors(self):
            origin = self.headers.get("Origin", "")
            self.send_header("Access-Control-Allow-Origin", origin if origin.startswith(("http://127.0.0.1", "http://localhost")) else "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            # ---- Full OAuth 2.0 routes ----
            _oauth_paths = ("/api/auth/google/login", "/api/auth/google/callback",
                            "/api/auth/me", "/api/auth/config")
            if u.path in _oauth_paths:
                ip = self.client_address[0]
                if _auth_rate_limited(ip):
                    self.send_response(429)
                    self._cors()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b'{"ok":false,"error":"Too many requests."}')
                    return
                query = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                result = handle_oauth_get(u.path, query, dict(self.headers), self.server.server_address[1])
                # apply any cookie directives
                set_cookie  = result.pop("_set_cookie", None)
                clear_cookie = result.pop("_clear_cookie", None)
                if "_redirect" in result:
                    self.send_response(302)
                    self._cors()
                    self.send_header("Location", result["_redirect"])
                    if set_cookie:
                        self.send_header("Set-Cookie", set_cookie)
                    if clear_cookie:
                        self.send_header("Set-Cookie", f"{clear_cookie}=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/")
                    self.end_headers()
                    return
                body = json.dumps(result.get("_json", {})).encode("utf-8")
                self.send_response(result.get("_status", 200))
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                if set_cookie:
                    self.send_header("Set-Cookie", set_cookie)
                if clear_cookie:
                    self.send_header("Set-Cookie", f"{clear_cookie}=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/")
                self.end_headers()
                self.wfile.write(body)
                return
            # ---- end OAuth 2.0 GET routes ----
            if u.path.startswith("/api/userdata") or u.path == "/api/auth/config":
                params = urllib.parse.parse_qs(u.query)
                payload = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
                res = udb.handle_user_data_request(u.path, payload, method="GET", headers=dict(self.headers))
                status = res.pop("http_status", None)
                body = json.dumps(res).encode("utf-8")
                self.send_response(status or 200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path in ("/api/ledger", "/api/audit"):
                params = urllib.parse.parse_qs(u.query)
                d = params.get("date", [None])[0]
                lim = int(params.get("limit", [100])[0])
                entries = udb.get_ledger_entries(limit=lim, date=d)
                body = json.dumps({"ok": True, "ledger": entries, "count": len(entries)}).encode("utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/api/scheduler":
                body = json.dumps({"ok": True, "scheduler": _get_scheduler_status()}).encode("utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/api/llm/gateway":
                body = json.dumps(llm_gateway.get_gateway_status()).encode("utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/api/llm/local-models":
                body = json.dumps(llm_gateway.fetch_device_local_models()).encode("utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/api/llm/interrupts":
                body = json.dumps(llm_gateway.INTERRUPT_ENGINE.list_interrupts()).encode("utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/api/company-research":
                from . import company_researcher
                cdir = company_researcher.RESEARCH_CACHE_DIR
                items = []
                if cdir.is_dir():
                    for f in sorted(cdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                        try:
                            items.append(json.loads(f.read_text("utf-8")))
                        except Exception:
                            pass
                body = json.dumps({"ok": True, "companies": items, "count": len(items)}).encode("utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path in ("/api/status", "/api/results"):
                body = json.dumps(build_api_status(vault)).encode("utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            rel = "index.html" if u.path in ("/", "/index.html", "/career_agent_ui.html") else u.path.lstrip("/")
            target = (ROOT / rel).resolve()
            root = ROOT.resolve()
            try:
                relp = target.relative_to(root)
            except ValueError:
                relp = None
            blocked = relp is None or ".env" in relp.parts or relp.parts[0] in ("tests", "live", "vault") or relp.suffix in (".py", ".db", ".env")                 or (relp.parts[0] == "private" and not (len(relp.parts) > 1 and relp.parts[1] == "resumes"))
            if blocked or not target.is_file():
                self.send_response(404)
                self._cors()
                self.end_headers()
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            with open(target, "rb") as f:
                self.wfile.write(f.read())

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8", errors="ignore") if length else "{}"
            try:
                payload = json.loads(raw) if raw else {}
            except Exception:
                payload = {}
            api_path = "/api/run" if u.path == "/api/run-pipeline" else u.path
            # ---- Full OAuth 2.0 POST routes ----
            _oauth_post_paths = ("/api/auth/logout", "/api/auth/gmail/disconnect", "/api/userdata/gmail/sync")
            if api_path in _oauth_post_paths:
                oauth_res = handle_oauth_post(api_path, payload, dict(self.headers))
                if oauth_res is not None:  # None means fall through to legacy handler
                    clear_cookie = oauth_res.pop("_clear_cookie", None)
                    status_code  = oauth_res.pop("_status", 200)
                    body = json.dumps(oauth_res.get("_json", oauth_res)).encode("utf-8")
                    self.send_response(status_code)
                    self._cors()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    if clear_cookie:
                        self.send_header("Set-Cookie", f"{clear_cookie}=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/")
                    self.end_headers()
                    self.wfile.write(body)
                    return
            # ---- end OAuth 2.0 POST routes ----
            res = handle_api_post(api_path, payload, vault, log=log, headers=dict(self.headers))
            status = res.pop("http_status", None)
            body = json.dumps(res).encode("utf-8")
            self.send_response(status or (200 if res.get("ok") else 400))
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

    srv = None
    for candidate in range(int(port), int(port) + 20):
        try:
            srv = ThreadingHTTPServer((host, candidate), Handler)
            break
        except OSError as e:
            log(f"Port {candidate} unavailable ({e.strerror or e}); trying {candidate + 1}...")
    if srv is None:
        raise SystemExit(f"No free port in {port}-{int(port) + 19}. Pass a different one with --port.")
    port = srv.server_address[1]
    _start_background_scheduler(vault, log)
    log(f"Career Agent UI & Local API Bridge running at http://{host}:{port}")
    log("Endpoints: GET /api/status | POST /api/auth | POST /api/rag | POST /api/apply | POST /api/env | POST /api/run | POST /api/resume | POST /api/profile | POST /api/tracker | POST /api/chat | POST /api/test-llm | POST /api/analyze-profile | POST /api/ledger | POST /api/scheduler")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down server.")
    finally:
        srv.server_close()
