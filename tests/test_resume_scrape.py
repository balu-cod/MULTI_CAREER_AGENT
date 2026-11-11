import json, os, pathlib, tempfile, unittest
from unittest import mock
from bs4 import BeautifulSoup
import career_agent_system as cli
from live import resume as R, scrape as SC, sources as S, runtime
from live.profile import check_profile
from live.vault import VaultAgent

PROFILE = {
    "full_name": "Asha Rao", "contact_email": "asha@example.com", "contact_phone": "+91 1234567890", "github": "https://github.com/asha", "location": "Hyderabad",
    "current_position": "Software Developer Intern", "technical_skills": ["Python", "FastAPI", "SQL", "Docker", "React", "Git"],
    "education": [{"degree": "B.Tech CSE", "school": "XYZ College", "period": "2022-2026"}], "certifications": [{"name": "Azure Fundamentals", "issuer": "Microsoft", "year": 2026}],
    "experience": [{"role": "Software Developer Intern", "company": "Acme", "period": "3 months", "bullets": ["Built REST endpoints with FastAPI and SQL", "Wrote Git workflow docs"], "skills": ["FastAPI"]}],
    "projects": [{"name": "Job Tracker API", "link": "https://github.com/asha/jt", "bullets": ["FastAPI service with SQL storage", "Dockerised and deployed"], "skills": ["FastAPI", "SQL", "Docker"]},
                 {"name": "Portfolio Site", "bullets": ["React single page site"], "skills": ["React"]}],
    "achievements": ["Won college hackathon"]}
JOB = {"id": "gh:x:1", "title": "Backend Python Intern", "company": "Foo", "desc": "We use Python, FastAPI, SQL, Kubernetes and Terraform. 5 years not needed."}


class ResumeBuildTests(unittest.TestCase):
    def test_relevant_project_first_and_skills_only_from_vault(self):
        d = R.build(PROFILE, JOB)
        self.assertEqual(d["projects"][0]["name"], "Job Tracker API")                    # React portfolio ranks below the FastAPI/SQL project
        flat = {s.lower() for _, vs in d["skills"] for s in vs}
        self.assertEqual(flat, {s.lower() for s in PROFILE["technical_skills"]})        # nothing added
        self.assertIn("kubernetes", d["missing"]); self.assertNotIn("kubernetes", flat)
        self.assertLess(d["ats"], 100); self.assertGreater(d["ats"], 0)

    def test_matching_skills_listed_first_within_group(self):
        langs = dict(R.build(PROFILE, JOB)["skills"])["Languages"]
        self.assertEqual(langs[0].lower(), "python")

    def test_base_resume_has_no_job_fields(self):
        d = R.build(PROFILE, None); self.assertIsNone(d["ats"]); self.assertIsNone(d["job"]); self.assertTrue(d["projects"])

    def test_empty_vault_sections_do_not_crash(self):
        d = R.build({"full_name": "A", "technical_skills": ["Python"]}, JOB); self.assertEqual((d["projects"], d["experience"], d["education"]), ([], [], []))

    def test_llm_summary_rejects_invented_claims(self):
        d = R.build(PROFILE, JOB)
        self.assertIsNone(R.llm_summary(PROFILE, d, JOB, lambda *a: "Expert in Kubernetes and Terraform with Python."))            # tech not in vault
        self.assertIsNone(R.llm_summary(PROFILE, d, JOB, lambda *a: "Built Python APIs that cut latency by 40%."))                  # number not in vault
        self.assertEqual(R.llm_summary(PROFILE, d, JOB, lambda *a: "Developer intern building FastAPI and SQL services."), "Developer intern building FastAPI and SQL services.")
        self.assertIsNone(R.llm_summary(PROFILE, d, JOB, lambda *a: None))

    def test_pdf_is_one_page_even_with_a_huge_vault(self):
        big = dict(PROFILE, projects=[{"name": f"Project {i}", "bullets": [f"Did thing {j} with Python and SQL for several users" * 2 for j in range(6)], "skills": ["Python"]} for i in range(8)],
                   experience=[{"role": f"Role {i}", "company": "C", "bullets": ["x " * 40] * 6} for i in range(5)], achievements=["a " * 30] * 3)
        out = pathlib.Path(tempfile.mkdtemp()) / "r.pdf"; info = R.render_pdf(R.build(big, JOB), out)
        self.assertEqual(info["pages"], 1); self.assertTrue(out.read_bytes().startswith(b"%PDF"))

    def test_pdf_survives_unicode_and_bad_links(self):
        p = dict(PROFILE, full_name="Zo\u00eb \u4e2d", github="javascript:alert(1)", projects=[{"name": "A <b>&", "link": "javascript:x", "bullets": ["\u2019quoted\u2019 \u2013 dash"]}])
        out = pathlib.Path(tempfile.mkdtemp()) / "u.pdf"; R.render_pdf(R.build(p, JOB), out); self.assertTrue(out.exists())

    def test_markdown_lists_what_not_to_claim(self):
        self.assertIn("kubernetes", R.render_md(R.build(PROFILE, JOB)).lower())

    def test_check_profile(self):
        self.assertEqual(check_profile(PROFILE), [])
        self.assertTrue(check_profile({"projects": "nope"})); self.assertTrue(check_profile({"projects": [{"bullets": ["x"]}]})); self.assertTrue(check_profile({"experience": [{"role": "r", "bullets": "str"}]}))


class CliTests(unittest.TestCase):
    def test_import_profile_splits_private_and_keeps_vault_valid(self):
        d, root = tempfile.mkdtemp(), pathlib.Path(tempfile.mkdtemp()); v = VaultAgent(vault_dir=d); v.bootstrap_defaults_if_empty()
        f = pathlib.Path(d) / "in.json"; f.write_text(json.dumps(PROFILE))
        with mock.patch.object(cli, "ROOT", root): cli.import_profile(v, str(f), lambda m: None)
        pub = v.load_artifact("user_profile_v1.json")                                  # would raise IntegrityError if the manifest were stale
        self.assertEqual(pub["projects"][0]["name"], "Job Tracker API"); self.assertNotIn("contact_phone", pub); self.assertIn("technical_skills", pub)
        self.assertEqual(json.loads((root / "private" / "profile.json").read_text())["contact_phone"], "+91 1234567890")

    def test_import_profile_rejects_bad_shape(self):
        d = tempfile.mkdtemp(); v = VaultAgent(vault_dir=d); f = pathlib.Path(d) / "bad.json"; f.write_text('{"projects": "x"}')
        with self.assertRaises(SystemExit): cli.import_profile(v, str(f), lambda m: None)

    def test_build_resume_from_job_text(self):
        d = tempfile.mkdtemp(); v = VaultAgent(vault_dir=d); v.save_artifact("user_profile_v1.json", {k: x for k, x in PROFILE.items() if k not in ("contact_phone",)})
        with mock.patch.object(cli, "ROOT", pathlib.Path(d)), mock.patch("live.profile.load_private", lambda: {}):
            data = cli.build_resume(v, "Python Backend Intern\nPython FastAPI Kubernetes", out_dir=d, log=lambda m: None)
        self.assertIn("kubernetes", data["missing"]); self.assertTrue((pathlib.Path(d) / "custom.pdf").exists())


LISTING = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"JobPosting","title":"Backend Intern","hiringOrganization":{"name":"Foo Inc"},
 "jobLocation":{"address":{"addressLocality":"Pune","addressCountry":"IN"}},"description":"&lt;p&gt;Python and SQL&lt;/p&gt;","datePosted":"2026-10-20","url":"https://foo.io/jobs/1?utm_source=x"},
 {"@type":"JobPosting","title":"Old Role","validThrough":"2020-01-01","description":"gone"}]}</script></head><body></body></html>"""
LIST2 = """<html><body><nav><a href="/careers">Careers</a><a href="mailto:hr@x.io">mail</a></nav>
<a href="/jobs/101">Python Developer Intern</a><a href="/jobs/102">Backend Engineer</a><a href="/about">About us</a><a href="https://other.com/jobs/9">Offsite Engineer</a><a href="/files/jd.pdf">Engineer JD</a>
<a rel="next" href="/careers?page=2">Next</a></body></html>"""
JOBPAGE = "<html><head><title>t</title></head><body><nav>menu</nav><main><h1>Python Developer Intern</h1><p>Location: Remote India</p><p>" + "We build things with Python and SQL. " * 15 + "</p></main><footer>foot</footer></body></html>"


class ScrapeTests(unittest.TestCase):
    def test_canon_drops_tracking(self): self.assertEqual(SC.canon("HTTPS://Foo.io/jobs/1/?utm_source=x&id=2#top"), "https://foo.io/jobs/1?id=2")

    def test_detect_ats_embeds(self):
        h = '<iframe src="https://boards.greenhouse.io/embed/job_board?for=acme"></iframe><a href="https://jobs.lever.co/beta/123">x</a><a href="https://acme.recruitee.com/o/x">y</a><a href="https://www.recruitee.com">z</a>'
        self.assertEqual(SC.detect_ats(h), [("greenhouse", "acme"), ("lever", "beta"), ("recruitee", "acme")])

    def test_jsonld_skips_expired_and_decodes_html(self):
        jobs = SC.jsonld_jobs(BeautifulSoup(LISTING, "html.parser"), "https://foo.io/careers")
        self.assertEqual(len(jobs), 1); j = jobs[0]
        self.assertEqual((j["title"], j["company"], j["location"], j["desc"]), ("Backend Intern", "Foo Inc", "Pune, IN", "Python and SQL")); self.assertEqual(j["id"], "pg:https://foo.io/jobs/1")

    def test_job_links_filters_navigation_files_and_offsite(self):
        links = SC.job_links(BeautifulSoup(LIST2, "html.parser"), "https://x.io/careers", SC.DEFAULT_KEYWORDS)
        self.assertEqual(sorted(links), ["https://x.io/jobs/101", "https://x.io/jobs/102"])

    def test_scrape_listing_follows_links_and_pagination(self):
        pages = {"https://x.io/careers": LIST2, "https://x.io/careers?page=2": '<a href="/jobs/103">Software Engineer Intern</a>', "https://x.io/jobs/101": JOBPAGE, "https://x.io/jobs/102": JOBPAGE.replace("Python Developer", "Backend Engineer"),
                 "https://x.io/jobs/103": JOBPAGE.replace("Python Developer", "Software Engineer")}
        out = SC.scrape_page("https://x.io/careers", None, pages.get, render=lambda u: None)
        self.assertEqual(sorted(j["url"] for j in out), ["https://x.io/jobs/101", "https://x.io/jobs/102", "https://x.io/jobs/103"])
        j = [x for x in out if x["url"].endswith("101")][0]
        self.assertEqual((j["title"], j["location"], j["company"]), ("Python Developer Intern", "Remote India", "x.io")); self.assertNotIn("menu", j["desc"]); self.assertNotIn("foot", j["desc"])

    def test_scrape_prefers_embedded_ats_api(self):
        html = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>'
        calls = []; fake = lambda g, slug: calls.append(slug) or [dict(id="gh:acme:1", portal="greenhouse", company="acme", title="Dev", location="", url="https://u/1", desc="d", posted=None)]
        with mock.patch.dict(S.REGISTRY, {"greenhouse": fake}):
            out = SC.scrape_page("https://acme.com/careers", None, lambda u: html)
        self.assertEqual((calls, out[0]["portal"]), (["acme"], "greenhouse"))

    def test_scrape_json_ld_listing_and_unavailable_page(self):
        out = SC.scrape_page({"url": "https://foo.io/careers", "company": "Foo"}, None, lambda u: LISTING)
        self.assertEqual((len(out), out[0]["company"]), (1, "Foo"))
        with self.assertRaises(RuntimeError): SC.scrape_page("https://foo.io/x", None, lambda u: None, render=lambda u: None)

    def test_js_only_page_uses_render_fallback(self):
        out = SC.scrape_page("https://foo.io/careers", None, lambda u: "<html><body><div id=app></div></body></html>", render=lambda u: LISTING)
        self.assertEqual(len(out), 1)


class ScannerTests(unittest.TestCase):
    def test_parallel_scan_keeps_order_dedupes_urls_and_isolates_failures(self):
        def g(url, timeout=25):
            if "boom" in url: raise RuntimeError("HTTP 500")
            if "greenhouse" in url:
                return {"jobs": [{"id": 1, "title": "Dev", "absolute_url": "https://a.io/1?utm_source=z", "content": "x", "location": {"name": "R"}}]}
            return [{"id": "7", "text": "Dev", "hostedUrl": "https://a.io/1", "categories": {}, "descriptionPlain": "y"}]      # same job via another portal
        ctx = {"vault": None, "profile": {"job_sources": {"greenhouse": ["g1"], "lever": ["l1", "boom"]}}, "log": lambda m: None, "insights": {}}
        runtime.discover()
        with mock.patch.dict(runtime.TOOLS, {"get_json": g}): runtime.AGENTS["scanner"]().run(ctx)
        self.assertEqual([j["portal"] for j in ctx["jobs"]], ["greenhouse"])                    # config order wins; tracking-param duplicate dropped
        h = {x["source"]: x for x in ctx["insights"]["source_health"]}; self.assertIn("500", h["lever:boom"]["error"]); self.assertIn("ms", h["greenhouse:g1"])

    def test_lever_falls_back_to_eu_host(self):
        seen = []
        def g(url):
            seen.append(url)
            if "api.lever.co" in url: raise RuntimeError("HTTP 404")
            return [{"id": "1", "text": "Dev", "hostedUrl": "https://jobs.eu.lever.co/c/1", "categories": {}, "descriptionPlain": "", "additionalPlain": ""}]
        self.assertEqual(len(S.lever(g, "c")), 1); self.assertTrue(seen[-1].startswith("https://api.eu.lever.co"))

    def test_recruitee_normalizes(self):
        out = S.recruitee(lambda u: {"offers": [{"id": 5, "title": "Dev", "careers_url": "https://c.recruitee.com/o/dev", "description": "<p>py</p>", "requirements": "<li>sql</li>", "remote": True, "published_at": "2026-10-01 10:00:00 UTC"}]}, "c")
        self.assertEqual((out[0]["location"], out[0]["desc"]), ("Remote", "py sql"))


if __name__ == "__main__": unittest.main()
