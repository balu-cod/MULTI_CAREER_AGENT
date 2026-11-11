"""End-to-end execution test: runs the real CLI and both HTTP servers as subprocesses in a throw-away copy of the project.
Offline-safe: network failures must degrade gracefully (that is part of what is being tested)."""
import json, os, pathlib, shutil, socket, subprocess, sys, tempfile, time, unittest, urllib.error, urllib.request

SRC = pathlib.Path(__file__).resolve().parent.parent
SKIP = shutil.ignore_patterns("__pycache__", "private", "secrets.env", "keys.json", "*.db", ".pytest_cache", "*.pdf")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cas_e2e_"))
        cls.root = cls.tmp / "proj"
        shutil.copytree(SRC, cls.root, ignore=SKIP)
        cls.env = {**os.environ, "USERDATA_DEV_AUTH": "1", "USERDATA_DB": str(cls.tmp / "u.db"), "APPLY_MODE": "off",
                   "DIGEST_SEND": "0", "PYTHONDONTWRITEBYTECODE": "1"}
        for k in ("GOOGLE_CLIENT_ID", "USERDATA_REQUIRE_AUTH", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "GMAIL_SMTP_USER", "GMAIL_SMTP_APP_PASSWORD"):
            cls.env.pop(k, None)
        cls.procs = []

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:
            p.terminate()
            try: p.wait(5)
            except Exception: p.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def cli(self, *args, timeout=240):
        r = subprocess.run([sys.executable, "career_agent_system.py", *args], cwd=self.root, env=self.env, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr

    def start(self, mode):
        port = free_port()
        p = subprocess.Popen([sys.executable, "career_agent_system.py", "--mode", mode, "--port", str(port)], cwd=self.root, env=self.env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), 0.3).close(); return port
            except OSError:
                time.sleep(0.25)
        self.fail(f"{mode} server did not start")

    def http(self, port, path, data=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try: return e.code, json.loads(raw)
            except Exception: return e.code, raw

    # ---- run in order: test_1 ... test_9
    def test_1_cli_offline_modes(self):
        rc, out = self.cli("--mode", "check-env"); self.assertEqual(rc, 0); self.assertIn("GOOGLE_CLIENT_ID", out)
        rc, out = self.cli("--mode", "import-profile", "--file", "profile.example.json"); self.assertEqual(rc, 0, out)
        self.assertTrue((self.root / "private" / "profile.json").is_file())
        rc, out = self.cli("--mode", "scrub-private"); self.assertEqual(rc, 0, out)
        rc, out = self.cli("--mode", "build-resume"); self.assertEqual(rc, 0, out)
        self.assertTrue((self.root / "private" / "resumes" / "_base.pdf").stat().st_size > 1000)
        rc, out = self.cli("--mode", "build-resume", "--job", "Backend intern: Python, FastAPI, SQL, Kubernetes"); self.assertEqual(rc, 0, out)
        self.assertTrue((self.root / "private" / "resumes" / "custom.pdf").is_file())

    def test_2_pipeline_runs_offline_and_writes_memory(self):
        rc, out = self.cli("--mode", "live-pipeline")
        self.assertEqual(rc, 0, out[-1500:])
        self.assertIn("RANKED FREE CERTIFICATIONS", out)
        self.assertTrue((self.root / "vault" / "memory" / "latest.json").is_file())
        rc, out = self.cli("--mode", "live-pipeline", "--strict")
        self.assertEqual(rc, 1, "--strict must fail when nothing could be fetched")

    def test_3_main_server_api_and_security(self):
        port = self.start("serve")
        st, body = self.http(port, "/api/status"); self.assertEqual(st, 200)
        from live import VERSION
        self.assertEqual(body["version"], VERSION); self.assertIn("userdata", body)
        st, body = self.http(port, "/"); self.assertEqual(st, 200); self.assertIn(b"<html", body.lower())
        for bad in ("/.env/secrets.env", "/live/server.py", "/private/profile.json", "/career_agent_system.py", "/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/private/user_data.db"):
            self.assertEqual(self.http(port, bad)[0], 404, bad)
        st, body = self.http(port, "/api/resume", {"job": "AI intern. Python, LangGraph, MCP, FastAPI", "title": "AI Intern"})
        self.assertEqual((st, body["ok"]), (200, True)); self.assertEqual(self.http(port, body["pdf_url"])[0], 200)
        st, body = self.http(port, "/api/tracker", {"id": "t1", "company": "Acme", "title": "Intern", "status": "Applied"})
        self.assertEqual((st, body["ok"]), (200, True), body)
        st, body = self.http(port, "/api/userdata/applications"); self.assertTrue(any(a["id"] == "t1" for a in body["applications"]))
        st, body = self.http(port, "/api/apply", {"job": {"title": "Backend Intern", "company": "Foo Inc", "hiringEmail": "hr@foo.io", "desc": "python sql"}})
        self.assertEqual((st, body["ok"]), (200, True), body)
        self.assertNotIn("Kodimurthy", json.dumps(body))
        self.assertEqual(self.http(port, "/api/nope", {})[0], 400)
        self.assertEqual(self.http(port, "/api/auth", {"email": "bad", "code": "x"})[0], 400)

    def test_4_oauth_through_main_server(self):
        port = self.start("serve")
        st, body = self.http(port, "/api/auth/google", {"email": "me@x.io", "name": "Me", "credential": "mock_google_oauth2_verified_token"})
        self.assertEqual((st, body["ok"], body["dev"]), (200, True, True))
        self.assertEqual(len(body["session_token"]), 43)
        st, body = self.http(port, "/api/userdata/profile", {"full_name": "Me", "email": "me@x.io", "phone": "1", "location": "Hyderabad"})
        self.assertEqual(st, 200)
        st, body = self.http(port, "/api/userdata/profile"); self.assertEqual(body["profile"]["location"], "Hyderabad")
        st, body = self.http(port, "/api/userdata/export"); self.assertEqual(st, 200); self.assertIn("candidate_profile", body)
        st, body = self.http(port, "/api/userdata/gmail/sync", {})
        self.assertEqual((st, body["ok"]), (400, False))

    def test_5_standalone_user_backend_and_required_auth(self):
        self.env["USERDATA_REQUIRE_AUTH"] = "1"
        try:
            port = self.start("user-backend")
        finally:
            self.env.pop("USERDATA_REQUIRE_AUTH")
        self.assertEqual(self.http(port, "/api/userdata/stats")[0], 401)
        tok = self.http(port, "/api/auth/google", {"email": "me@x.io"})[1]["session_token"]
        auth = {"Authorization": "Bearer " + tok}
        st, body = self.http(port, "/api/userdata/stats", headers=auth); self.assertEqual((st, body["ok"]), (200, True))
        self.http(port, "/api/userdata/logout", {}, headers=auth)
        self.assertEqual(self.http(port, "/api/userdata/stats", headers=auth)[0], 401)

    def test_6_no_secrets_or_personal_data_shipped(self):
        bad = []
        for p in SRC.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".md", ".json", ".example") and "private" not in p.parts and "vault" not in p.parts and p.name not in ("test_e2e.py", "keys.json", "secrets.env"):
                t = p.read_text("utf-8", "ignore")
                if "8688031654" in t or "kodimurthybalu" in t:
                    bad.append(str(p.relative_to(SRC)))
        self.assertEqual(bad, [], "hardcoded personal data in source")


if __name__ == "__main__":
    unittest.main(verbosity=2)
