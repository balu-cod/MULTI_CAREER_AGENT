import datetime as dt, os, pathlib, smtplib, tempfile, unittest
from unittest import mock
from live import runtime, sources as S, mailer as M, outbox
from live.vault import VaultAgent


def mk():
    d = tempfile.mkdtemp(); v = VaultAgent(vault_dir=d, audit_path=d + "/audit.log"); v.bootstrap_defaults_if_empty(); runtime.discover(); return v


FIX = {
    "boards-api.greenhouse.io": {"jobs": [{"id": 1, "title": "Python Intern", "location": {"name": "Remote"}, "absolute_url": "https://gh/1", "content": "&lt;p&gt;python sql&lt;/p&gt;", "first_published": "2026-10-30T10:00:00Z"}]},
    "api.lever.co": [{"id": "a", "text": "Dev Intern", "categories": {"location": "India"}, "hostedUrl": "https://lv/a", "descriptionPlain": "python", "createdAt": 1793000000000}],
    "api.ashbyhq.com": {"jobs": [{"id": "x", "title": "Backend Intern", "location": "Remote", "jobUrl": "https://ab/x", "descriptionPlain": "python", "publishedAt": "2026-10-30T10:00:00Z"}, {"id": "y", "title": "Hidden", "isListed": False, "jobUrl": "https://ab/y"}]},
    "apply.workable.com": {"name": "WK Co", "jobs": [{"title": "Dev", "shortcode": "S1", "url": "https://wk/1", "city": "Pune", "country": "India", "description": "<b>python</b>", "published_on": "2026-10-29"}]},
    "remotive.com": {"jobs": [{"id": 5, "company_name": "RM", "title": "Python Dev", "url": "https://rm/5", "description": "<p>python</p>", "publication_date": "2026-10-30T00:00:00"}]},
    "remoteok.com": [{"legal": "notice"}, {"id": "9", "position": "Python Engineer", "company": "RO", "url": "https://ro/9", "description": "python", "tags": ["python"], "date": "2026-10-30T00:00:00+00:00"}],
    "arbeitnow.com": {"data": [{"slug": "s", "company_name": "AN", "title": "Dev Intern", "url": "https://an/s", "description": "python", "tags": [], "remote": True, "created_at": 1793000000}]},
    "hn.algolia.com/api/v1/search_by_date": {"hits": [{"objectID": "100"}]},
    "hn.algolia.com/api/v1/search?": {"hits": [{"objectID": "101", "parent_id": 100, "comment_text": "Acme | Python Intern | Remote | <p>apply</p>", "created_at": "2026-10-30T00:00:00Z"}, {"objectID": "102", "parent_id": 101, "comment_text": "reply"}]},
}

def fake_get_json(url, timeout=25):
    for k, v in FIX.items():
        if k in url: return v
    raise RuntimeError("404 " + url)


class SourceTests(unittest.TestCase):
    def test_every_source_normalizes(self):
        need = {"id", "portal", "company", "title", "location", "url", "desc", "posted"}
        calls = [("greenhouse", "b"), ("lever", "c"), ("ashby", "o"), ("workable", "w"), ("remotive", None), ("remoteok", None), ("arbeitnow", None), ("hn_hiring", None)]
        for name, arg in calls:
            out = S.REGISTRY[name](fake_get_json, arg)
            self.assertTrue(out, name)
            for j in out: self.assertTrue(need <= set(j), name); self.assertTrue(j["url"], name)
        self.assertEqual(len(S.ashby(fake_get_json, "o")), 1)                    # unlisted posting skipped
        self.assertEqual(S.arbeitnow(fake_get_json)[0]["posted"][:4], "2026")    # epoch seconds converted
        self.assertEqual(len(S.hn_hiring(fake_get_json)), 1)                     # replies are not postings
        self.assertIn("python sql", S.greenhouse(fake_get_json, "b")[0]["desc"])  # escaped HTML decoded

    def test_scanner_health_dedupe_and_failures(self):
        v = mk(); prof = {"job_sources": {"greenhouse": ["b"], "lever": ["c"], "ashby": ["o"], "workable": ["w"], "remotive": True, "remoteok": True, "arbeitnow": True, "hn_hiring": True, "pages": []}}
        ctx = {"vault": v, "profile": prof, "log": lambda m: None, "insights": {}}
        with mock.patch.dict(runtime.TOOLS, {"get_json": fake_get_json}), mock.patch.object(S, "DELAY", 0):
            runtime.AGENTS["scanner"]().run(ctx)
        self.assertEqual(len(ctx["jobs"]), 8); self.assertTrue(all(h["count"] for h in ctx["insights"]["source_health"]))
        broken = {"job_sources": {"greenhouse": ["b"], "lever": ["zzz-missing"]}}
        def partly(url, timeout=25):
            if "zzz" in url: raise RuntimeError("HTTP 404")
            return fake_get_json(url)
        ctx = {"vault": v, "profile": broken, "log": lambda m: None, "insights": {}}
        with mock.patch.dict(runtime.TOOLS, {"get_json": partly}), mock.patch.object(S, "DELAY", 0):
            runtime.AGENTS["scanner"]().run(ctx)
        h = {x["source"]: x for x in ctx["insights"]["source_health"]}
        self.assertEqual(len(ctx["jobs"]), 1); self.assertIn("404", h["lever:zzz-missing"]["error"])      # one bad source never kills the run


class FakeSMTP:
    sent, fail_auth, fail_times = [], False, 0
    def __init__(self, host, port, timeout=None): self.host = host
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, u, p):
        if FakeSMTP.fail_auth: raise smtplib.SMTPAuthenticationError(535, b"bad")
        FakeSMTP.login_args = (u, p)
    def send_message(self, m):
        if FakeSMTP.fail_times > 0: FakeSMTP.fail_times -= 1; raise smtplib.SMTPServerDisconnected("dropped")
        FakeSMTP.sent.append(m)


class MailTests(unittest.TestCase):
    def setUp(self):
        FakeSMTP.sent, FakeSMTP.fail_auth, FakeSMTP.fail_times = [], False, 0
        self.v = mk(); self.m = M.Mailer("me@gmail.com", "abcd efgh ijkl mnop", self.v)
        self.p = mock.patch("smtplib.SMTP_SSL", FakeSMTP); self.p.start(); self.t = mock.patch("time.sleep"); self.t.start()
    def tearDown(self): self.p.stop(); self.t.stop()

    def test_send_logs_in_with_spaceless_app_password_and_audits(self):
        r = self.m.send("hr@acme.com", "Hi", "body"); self.assertEqual(r["status"], "sent")
        self.assertEqual(FakeSMTP.login_args, ("me@gmail.com", "abcdefghijklmnop")); self.assertEqual(self.m.sent_today(), 1)

    def test_retries_transient_then_succeeds(self):
        FakeSMTP.fail_times = 2; self.assertEqual(self.m.send("hr@acme.com", "Hi", "b")["status"], "sent")

    def test_auth_error_is_actionable_and_not_retried(self):
        FakeSMTP.fail_auth = True
        with self.assertRaisesRegex(M.MailError, "App Password"): self.m.send("hr@acme.com", "Hi", "b")

    def test_rejects_bad_addresses_and_header_injection(self):
        for to in ("nope", "a@b", "x@y.com\r\nBcc: z@z.com"):
            with self.assertRaises(M.MailError): self.m.send(to, "s", "b")
        with self.assertRaises(M.MailError): self.m.send("hr@acme.com", "Hi\r\nBcc: z@z.com", "b")

    def test_daily_cap_and_dry_run(self):
        self.m.daily_cap = 1; self.m.send("a@b.com", "s", "b")
        with self.assertRaisesRegex(M.MailError, "cap"): self.m.send("a@b.com", "s", "b")
        d = M.Mailer("me@gmail.com", "x", self.v, dry_run=True); n = len(FakeSMTP.sent); self.assertEqual(d.send("a@b.com", "s", "b")["status"], "dry-run"); self.assertEqual(len(FakeSMTP.sent), n)

    def test_digest_html_is_escaped_and_has_attachment_support(self):
        r = {"updated": "2026-11-01T08:00:00", "scanned": 3, "jobs": [{"score": 80, "title": "<script>x</script>", "company": "A&B", "url": "javascript:alert(1)", "ats": 70}]}
        text, body = M.render_digest(r, {"source_health": [{"source": "lever:x", "count": 0, "error": "HTTP 404"}]})
        self.assertNotIn("<script>", body); self.assertNotIn('href="javascript', body); self.assertIn("A&amp;B", body); self.assertIn("SOURCE PROBLEMS", text)
        pdf = pathlib.Path(tempfile.mkdtemp()) / "cv.pdf"; pdf.write_bytes(b"%PDF-1.4 x")
        msg = self.m.build("hr@acme.com", "s", "b", body, [pdf]); self.assertEqual([p.get_filename() for p in msg.iter_attachments()], ["cv.pdf"])

    def test_outbox_needs_recipient_and_explicit_yes(self):
        root = pathlib.Path(tempfile.mkdtemp()); (root / "private" / "drafts").mkdir(parents=True); (root / "private" / "resumes").mkdir()
        (root / "private" / "drafts" / "a.txt").write_text("To: hr@acme.com\nSubject: Application\nJob: u\n\nHello")
        (root / "private" / "drafts" / "b.txt").write_text("To: \nSubject: No recipient\n\nHi")
        (root / "private" / "resumes" / "a.pdf").write_bytes(b"%PDF-1.4 x")
        env = {"GMAIL_SMTP_USER": "me@gmail.com", "GMAIL_SMTP_APP_PASSWORD": "pw"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(outbox.send_drafts(self.v, lambda m: None, ask=lambda q: "n", root=root)["sent"], 0)       # declined -> nothing sent
            self.assertEqual(FakeSMTP.sent, [])
            res = outbox.send_drafts(self.v, lambda m: None, ask=lambda q: "y", root=root)
        self.assertEqual(res["sent"], 1); self.assertEqual(len(FakeSMTP.sent), 1)
        self.assertEqual([p.get_filename() for p in FakeSMTP.sent[0].iter_attachments()], ["a.pdf"])
        self.assertTrue((root / "private" / "sent" / "a.txt").exists()); self.assertTrue((root / "private" / "drafts" / "b.txt").exists())
