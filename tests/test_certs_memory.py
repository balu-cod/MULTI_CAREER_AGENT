import json, tempfile, unittest, pathlib
from unittest import mock
from live import runtime, certsources as C, analysis as A
from live.vault import VaultAgent
from live.memory import write_run

MS = {"learningPaths": [
    {"title": "Build APIs with FastAPI", "summary": "Python web APIs", "url": "https://learn.microsoft.com/training/paths/fastapi/", "levels": ["beginner"], "products": ["azure"], "roles": ["developer"], "duration_in_minutes": 300},
    {"title": "Advanced Kubernetes ops", "summary": "clusters", "url": "https://learn.microsoft.com/training/paths/k8s/", "levels": ["advanced"], "products": [], "roles": [], "duration_in_minutes": 600},
    {"title": "Excel basics", "summary": "spreadsheets", "url": "https://learn.microsoft.com/training/paths/excel/", "levels": ["beginner"], "products": [], "roles": []}]}
README = "# Google\n- [Intro to MCP agents](https://cloud.example/mcp) - free badge\n![x](https://img.shields.io/a.svg)\n# Misc\n- [Cooking 101](https://x.example/c)\n"
PROFILE = {"handle": "h", "current_position": "Software Developer Intern", "technical_skills": ["Python", "Git"], "skill_gaps": ["kubernetes"], "interests": ["mcp"],
           "contact_email": "secret@mail.com", "contact_phone": "999"}


def mk():
    d = tempfile.mkdtemp(); v = VaultAgent(vault_dir=d, audit_path=d + "/a.log"); v.bootstrap_defaults_if_empty(); return v


class CertTests(unittest.TestCase):
    def analysis(self, **kw): return {"level": "beginner", "terms": ["fastapi", "kubernetes", "mcp"], **kw}

    def test_analysis_uses_vault_profile(self):
        a = A.analyze(PROFILE, [1, 2], [{"skills": ["python"]}, {"skills": ["python", "git"]}], ["fastapi"])
        self.assertEqual(a["level"], "beginner"); self.assertEqual(a["strengths"][0], "python"); self.assertEqual(a["terms"][:3], ["fastapi", "kubernetes", "mcp"])
        self.assertNotIn("python", a["terms"])                                       # skills you already have are not learning targets

    def test_collect_ranks_filters_and_flags_new(self):
        g = lambda u: MS if "learningPaths" in u else {"certifications": []}
        alive = lambda u: "k8s" not in u
        final, health = C.collect(self.analysis(), g, lambda u: README, alive, [{"name": "Docker Get Started", "url": "https://docs.docker.com/", "tags": ["docker"]}], seen={"https://cloud.example/mcp"})
        names = [c["name"] for c in final]
        self.assertEqual(names[0], "Build APIs with FastAPI")                        # beginner-level match ranks first
        self.assertNotIn("Excel basics", names); self.assertNotIn("Advanced Kubernetes ops", names)   # no term match / dead URL
        self.assertNotIn("Cooking 101", names); self.assertFalse(next(c for c in final if c["url"].endswith("/mcp"))["new"])
        self.assertTrue(all(c["free_claim"] and c["verified_live"] for c in final)); self.assertTrue(all(h["error"] is None for h in health))

    def test_one_dead_source_does_not_stop_others(self):
        def g(u): raise RuntimeError("HTTP 503")
        final, health = C.collect(self.analysis(), g, lambda u: README, lambda u: True, [])
        errs = {h["source"]: h["error"] for h in health}
        self.assertIn("503", errs["mslearn-paths"]); self.assertIsNone(errs["community-free-list"]); self.assertEqual(len(final), 1)


class MemoryTests(unittest.TestCase):
    def ctx(self, v, ids, **kw):
        m = [dict(id=i, title="T" + i, company="C", score=70, url="https://x/" + i, skills=["python"], posted=None) for i in ids]
        return {"vault": v, "profile": dict(PROFILE, memory_keep=2), "log": lambda s: None, "run_log": ["scan ok https://api/x?key=SECRET1"], "failed": {"digest"}, "jobs": m, "matches": m,
                "insights": {"certs": [{"name": "Cert", "url": "https://c/1", "provider": "P", "free_claim": "free", "new": True}], "today": {"date": "d", "morning_7am": "Study"}}, **kw}

    def test_memory_file_content_diff_and_privacy(self):
        v = mk(); e1 = write_run(self.ctx(v, ["a", "b"])); e2 = write_run(self.ctx(v, ["b", "c"]))
        self.assertEqual(e1["new_jobs"], 2); self.assertEqual(e2["new_jobs"], 1)               # only 'c' is new on run 2
        mdir = pathlib.Path(v.dir) / "memory"; run = json.loads((mdir / e2["file"]).read_text())
        blob = json.dumps(run); self.assertNotIn("secret@mail.com", blob); self.assertNotIn("999", blob); self.assertNotIn("SECRET1", blob)   # no contact details, key redacted
        self.assertIn("agent failed or skipped: digest", run["errors"]); self.assertEqual(run["jobs"]["gone_since_last_run"], 1)
        self.assertTrue((mdir / e2["summary"]).read_text().startswith("# Run")); self.assertEqual(json.loads((mdir / "latest.json").read_text())["run_id"], run["run_id"])

    def test_two_runs_same_second_do_not_overwrite_and_retention_prunes(self):
        v = mk(); c = self.ctx(v, ["a"], run_id="20260101T000000Z")
        files = [write_run(dict(c))["file"] for _ in range(3)]
        self.assertEqual(len(set(files)), 3)
        idx = json.loads((pathlib.Path(v.dir) / "memory" / "index.json").read_text())["runs"]
        self.assertEqual(len(idx), 2)                                                         # memory_keep=2
        self.assertFalse((pathlib.Path(v.dir) / "memory" / files[0]).exists())


class PipelineMemoryTest(unittest.TestCase):
    def test_pipeline_writes_memory_even_if_an_agent_fails(self):
        from live.agents import Scanner, Digest
        from tests.test_pipeline import jobs
        v = mk(); runtime.discover()
        patches = {"url_alive": lambda u: True, "ask_llm": lambda *a, **k: None, "get_json": lambda u: MS if "learningPaths" in u else {"hits": [], "items": [], "certifications": []}, "fetch": lambda u: None, "get_text": lambda u: README}
        def boom(self, ctx): raise RuntimeError("smtp exploded")
        with mock.patch.dict(runtime.TOOLS, patches), mock.patch.object(Scanner, "run", lambda self, ctx: ctx.__setitem__("jobs", jobs())), mock.patch.object(Digest, "run", boom), \
             mock.patch.dict("os.environ", {"APPLY_MODE": "off"}):
            runtime.run_pipeline(v, lambda m: None)
        latest = json.loads((pathlib.Path(v.dir) / "memory" / "latest.json").read_text())
        self.assertIn("agent failed or skipped: digest", latest["errors"]); self.assertEqual(latest["jobs"]["matched"], 2)
        self.assertTrue(latest["certs"]); self.assertEqual(latest["analysis"]["level"], "beginner"); self.assertNotIn("contact_email", latest["user"])
