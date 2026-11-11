import os, tempfile, time, unittest
from unittest import mock
from live import user_data_backend as udb


class UserBackendTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"USERDATA_DB": os.path.join(self.td, "t.db")}, clear=False)
        self.env.start()
        for k in ("GOOGLE_CLIENT_ID", "USERDATA_DEV_AUTH", "USERDATA_REQUIRE_AUTH"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def claims(self, **kw):
        c = {"aud": "cid", "iss": "https://accounts.google.com", "exp": str(int(time.time()) + 600), "email": "a@b.co", "email_verified": "true", "name": "A B"}
        c.update(kw)
        return c

    def test_verify_token_paths(self):
        ok, err = udb.verify_google_id_token("t", "cid", fetch=lambda u: self.claims())
        self.assertIsNone(err); self.assertEqual(ok["email"], "a@b.co")
        for bad in (self.claims(aud="other"), self.claims(iss="evil.com"), self.claims(exp="1"), self.claims(email_verified="false")):
            self.assertIsNotNone(udb.verify_google_id_token("t", "cid", fetch=lambda u, b=bad: b)[1])
        self.assertIn("not configured", udb.verify_google_id_token("t", "")[1])

    def test_mock_token_rejected_without_client_id(self):
        r = udb.handle_user_data_request("/api/auth/google", {"email": "a@b.co", "credential": "mock_google_oauth2_verified_token"})
        self.assertFalse(r["ok"])

    def test_dev_auth_flag_and_session(self):
        os.environ["USERDATA_DEV_AUTH"] = "1"
        r = udb.handle_user_data_request("/api/auth/google", {"email": "a@b.co", "name": "A"})
        self.assertTrue(r["ok"] and r["dev"])
        self.assertEqual(udb.session_from_token(r["session_token"])["email"], "a@b.co")
        self.assertIsNone(udb.session_from_token("nope"))

    def test_require_auth(self):
        os.environ["USERDATA_REQUIRE_AUTH"] = "1"; os.environ["USERDATA_DEV_AUTH"] = "1"
        self.assertEqual(udb.handle_user_data_request("/api/userdata/stats", method="GET")["http_status"], 401)
        tok = udb.handle_user_data_request("/api/auth/google", {"email": "a@b.co"})["session_token"]
        self.assertTrue(udb.handle_user_data_request("/api/userdata/stats", method="GET", headers={"Authorization": "Bearer " + tok})["ok"])
        udb.handle_user_data_request("/api/userdata/logout", {}, headers={"Authorization": "Bearer " + tok})
        self.assertIsNone(udb.session_from_token(tok))

    def test_token_not_stored_plain(self):
        os.environ["USERDATA_DEV_AUTH"] = "1"
        tok = udb.handle_user_data_request("/api/auth/google", {"email": "a@b.co"})["session_token"]
        with udb._connect() as con:
            self.assertNotIn(tok, str([tuple(r) for r in con.execute("SELECT * FROM oauth_sessions")]))

    def test_profile_roundtrip_and_validation(self):
        self.assertFalse(udb.update_candidate_profile({"email": "bad"})["ok"])
        udb.handle_user_data_request("/api/userdata/profile", {"full_name": "X", "email": "x@y.zz", "phone": "1", "location": "L", "password": "secret"})
        p = udb.handle_user_data_request("/api/userdata/profile", method="GET")["profile"]
        self.assertEqual(p["full_name"], "X"); self.assertNotIn("password", p)

    def test_applications_and_stats(self):
        udb.save_user_application({"id": "a1", "job_title": "T", "company": "C", "hiring_email": "h@c.io"})
        udb.save_user_application({"id": "a1", "job_title": "T", "company": "C", "status": "Interview"})
        apps = udb.handle_user_data_request("/api/userdata/applications", method="GET")["applications"]
        self.assertEqual(len(apps), 1); self.assertEqual(apps[0]["status"], "Interview")
        st = udb.get_user_data_stats()
        self.assertEqual(st["tables"]["contacts"], 1); self.assertGreaterEqual(st["database"]["size_kb"], 0)

    def test_gmail_sync_fake_imap_dedupes(self):
        raw = b"From: Rec <rec@co.com>\r\nSubject: Interview\r\nDate: Mon, 02 Nov 2026 10:00:00 +0000\r\nMessage-ID: <1@x>\r\nContent-Type: text/plain\r\n\r\nHello there"
        class M:
            def login(s, u, p): pass
            def select(s, *a, **k): return ("OK", [b"1"])
            def search(s, *a): return ("OK", [b"1"])
            def fetch(s, i, spec): return ("OK", [(b"1", raw)])
            def logout(s): pass
        r1 = udb.sync_gmail("me@g.com", "abcd efgh ijkl mnop", imap_factory=M)
        r2 = udb.sync_gmail("me@g.com", "abcd efgh ijkl mnop", imap_factory=M)
        self.assertEqual((r1["new_messages"], r2["new_messages"], r2["total_stored"]), (1, 0, 1))
        self.assertFalse(udb.sync_gmail("", "")["ok"])
        with udb._connect() as con:
            self.assertNotIn("abcd", str([tuple(r) for r in con.execute("SELECT * FROM gmail_messages")]))


if __name__ == "__main__":
    unittest.main()



    def test_contacts_crud_and_application_delete(self):
        r1 = udb.handle_user_data_request("/api/userdata/contacts", {
            "name": "Ananya Sharma",
            "company": "Razorpay",
            "email": "ananya.recruiting@razorpay.com",
            "phone": "+91 80 4111 2222",
            "notes": "AI Platform Intern"
        }, method="POST")
        self.assertTrue(r1["ok"])
        r2 = udb.handle_user_data_request("/api/userdata/contacts", method="GET")
        self.assertTrue(any(c["email"] == "ananya.recruiting@razorpay.com" for c in r2["contacts"]))
        r3 = udb.handle_user_data_request("/api/userdata/contacts", {
            "action": "delete",
            "email": "ananya.recruiting@razorpay.com"
        }, method="POST")
        self.assertTrue(r3["ok"])
        self.assertFalse(any(c["email"] == "ananya.recruiting@razorpay.com" for c in r3["contacts"]))


class SignInBackendTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"USERDATA_DB": os.path.join(self.td, "s.db")})
        self.env.start()
        for k in ("GOOGLE_CLIENT_ID", "USERDATA_DEV_AUTH", "USERDATA_REQUIRE_AUTH", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "GMAIL_SMTP_USER", "GMAIL_SMTP_APP_PASSWORD"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_auth_config(self):
        c = udb.handle_user_data_request("/api/auth/config", method="GET")
        self.assertEqual((c["oauth_configured"], c["google_client_id"], c["dev_auth"]), (False, "", False))
        os.environ["USERDATA_DEV_AUTH"] = "1"
        self.assertTrue(udb.auth_config()["dev_auth"])
        os.environ["GOOGLE_CLIENT_ID"] = "abc.apps.googleusercontent.com"
        c = udb.auth_config()
        self.assertEqual((c["oauth_configured"], c["dev_auth"]), (True, False))   # dev mode is off once real OAuth is configured

    def test_verify_gmail_login(self):
        import imaplib
        good = "abcd efgh ijkl mnop"
        class Ok:
            def login(s, u, p): self.seen = (u, p)
            def logout(s): pass
        self.assertEqual(udb.verify_gmail_login("me@gmail.com", good, lambda: Ok()), (True, None))
        self.assertEqual(self.seen, ("me@gmail.com", "abcdefghijklmnop"))
        self.assertFalse(udb.verify_gmail_login("nope", good)[0])
        self.assertIn("16", udb.verify_gmail_login("me@gmail.com", "short")[1])
        class Rej:
            def login(s, u, p): raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        ok, err = udb.verify_gmail_login("me@gmail.com", good, lambda: Rej())
        self.assertFalse(ok); self.assertIn("rejected", err)
        def boom(): raise OSError("no network")
        ok, err = udb.verify_gmail_login("me@gmail.com", good, boom)
        self.assertFalse(ok); self.assertIn("Could not reach Gmail", err)

    def test_api_auth_only_persists_after_gmail_accepts(self):
        from live.vault import VaultAgent
        from live import server
        v = VaultAgent(vault_dir=self.td + "/v"); v.bootstrap_defaults_if_empty()
        with mock.patch.object(server, "set_secret") as ss, mock.patch.object(server, "load_env"):
            with mock.patch.object(udb, "verify_gmail_login", return_value=(False, "rejected")):
                r = server.handle_api_post("/api/auth", {"email": "me@gmail.com", "code": "abcdefghijklmnop"}, v)
            self.assertEqual((r["ok"], r["error"]), (False, "rejected")); ss.assert_not_called()
            with mock.patch.object(udb, "verify_gmail_login", return_value=(True, None)):
                r = server.handle_api_post("/api/auth", {"email": "Me@Gmail.com", "code": "abcd efgh ijkl mnop"}, v)
            self.assertTrue(r["ok"]); self.assertEqual(r["email"], "me@gmail.com"); self.assertEqual(ss.call_count, 2)
            self.assertEqual(udb.session_from_token(r["session_token"])["provider"], "app_password")
            r = server.handle_api_post("/api/auth", {"use_configured": True}, v)
            self.assertFalse(r["ok"]); self.assertIn("No saved Gmail credentials", r["error"])
