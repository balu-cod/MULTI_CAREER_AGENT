"""Turns the Vault profile + this run's live jobs into a small analysis the other agents use (and the memory file records)."""
import json, pathlib, re
from collections import Counter

SNAPSHOT_KEYS = ("handle", "current_position", "target_roles", "technical_skills", "skill_gaps", "interests", "preferred_locations", "availability",
                 "match_threshold", "apply_threshold", "max_age_days")      # explicit allowlist: never contact details


def level_of(profile):
    text = f"{profile.get('current_position', '')} {profile.get('education', '')}".lower()
    return "beginner" if re.search(r"intern|fresher|student|trainee|junior|b\.?tech|graduate", text) else "intermediate"


def analyze(profile, jobs, matches, gaps):
    skills = [s.lower() for s in profile.get("technical_skills", [])]
    strengths = [k for k, _ in Counter(s.lower() for j in matches for s in j.get("skills", [])).most_common(6)] or skills[:6]
    terms = []
    for t in list(gaps) + [g.lower() for g in profile.get("skill_gaps", [])] + [i.lower() for i in profile.get("interests", [])]:
        if t and t not in terms and t not in skills: terms.append(t)
    return {"level": level_of(profile), "strengths": strengths, "terms": terms[:12], "target_roles": profile.get("target_roles", []),
            "jobs_seen": len(jobs), "jobs_matched": len(matches)}


def memory_dir(vault): return pathlib.Path(vault.dir) / "memory"


def latest_memory(vault):
    p = memory_dir(vault) / "latest.json"
    try: return json.loads(p.read_text("utf-8")) if p.exists() else None
    except (OSError, json.JSONDecodeError): return None
