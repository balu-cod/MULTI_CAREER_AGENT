"""Drives the real sign-in screen in headless Chromium against the real HTTP server (in-process).
Only the things that need the internet are faked: Google's gsi script and the Gmail IMAP / Google token checks."""
import os, pathlib, socket, tempfile, threading, time, unittest
from unittest import mock

try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = True
except Exception:  # pragma: no cover
    HAVE_PW = False

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAKE_GIS = """window.google={accounts:{id:{initialize:function(o){window.__gcb=o.callback;window.__gcid=o.client_id},
renderButton:function(el){var b=document.createElement('button');b.id='fake-g';b.textContent='Sign in with Google';b.onclick=function(){window.__gcb({credential:'fake-id-token'})};el.appendChild(b)},
disableAutoSelect:function(){}}}};"""


APPBTN = "#view-signin button[onclick*=handleSignInWithAppCode]"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@unittest.skipUnless(HAVE_PW, "playwright not installed")
class SignInBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.env = mock.patch.dict(os.environ, {"USERDATA_DB": os.path.join(cls.tmp, "b.db")})
        cls.env.start()
        for k in ("GOOGLE_CLIENT_ID", "USERDATA_DEV_AUTH", "USERDATA_REQUIRE_AUTH", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "GMAIL_SMTP_USER", "GMAIL_SMTP_APP_PASSWORD"):
            os.environ.pop(k, None)
        # never write the real project's .env/ during tests
        cls.p1 = mock.patch("live.server.set_secret", lambda *a, **k: {}); cls.p1.start()
        cls.p2 = mock.patch("live.server.load_env", lambda *a, **k: None); cls.p2.start()
        from live.vault import VaultAgent
        from live.server import serve
        v = VaultAgent(vault_dir=cls.tmp + "/vault"); v.bootstrap_defaults_if_empty()
        cls.port = free_port()
        threading.Thread(target=serve, args=(v, "127.0.0.1", cls.port, lambda m: None), daemon=True).start()
        for _ in range(40):
            try: socket.create_connection(("127.0.0.1", cls.port), 0.3).close(); break
            except OSError: time.sleep(0.2)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.p1.stop(); cls.p2.stop(); cls.env.stop()

    def page(self):
        ctx = self.browser.new_context()
        pg = ctx.new_page()
        def route(r):
            u = r.request.url
            if u.startswith(f"http://127.0.0.1:{self.port}"): return r.continue_()
            if "accounts.google.com/gsi/client" in u: return r.fulfill(body=FAKE_GIS, content_type="application/javascript")
            if "lucide" in u: return r.fulfill(body="window.lucide={createIcons:function(){}};", content_type="application/javascript")
            if "tailwind" in u: return r.fulfill(body="window.tailwind={};", content_type="application/javascript")
            if u.endswith(".js"): return r.fulfill(body="", content_type="application/javascript")
            if "fonts.googleapis" in u: return r.fulfill(body="", content_type="text/css")
            return r.abort()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.route("**/*", route)
        pg.goto(f"http://127.0.0.1:{self.port}/")
        pg.wait_for_selector("#google-signin-slot p, #google-signin-slot button", timeout=10000)
        return pg

    def signed_in(self, pg):
        return "hidden" in (pg.get_attribute("#view-signin", "class") or "")

    def err(self, pg):
        pg.wait_for_function("document.getElementById('signin-error') && !document.getElementById('signin-error').classList.contains('hidden')", timeout=8000)
        return pg.inner_text("#signin-error")

    def test_0_page_scripts_load_without_errors(self):
        pg = self.page()
        self.assertEqual(pg.errors, [])                       # a SyntaxError here means the app script never ran
        self.assertTrue(pg.evaluate("typeof currentProfile === 'object' && typeof showToast === 'function'"))

    def test_1_screen_has_no_prefilled_identity_and_explains_google_setup(self):
        pg = self.page()
        self.assertEqual(pg.input_value("#signin-email-input"), "")
        self.assertIn("not configured", pg.inner_text("#google-signin-slot"))
        self.assertEqual(pg.locator("#view-signin button[onclick*=handleGoogleOAuthSignIn]").count(), 0)  # fake button gone
        self.assertEqual(pg.input_value("#vault-backend-url-input"), f"http://127.0.0.1:{self.port}")

    def test_2_client_side_validation_does_not_sign_in(self):
        pg = self.page()
        pg.fill("#signin-email-input", "not-an-email"); pg.click(APPBTN)
        self.assertIn("valid Gmail", self.err(pg)); self.assertFalse(self.signed_in(pg))
        pg.fill("#signin-email-input", "a@gmail.com"); pg.fill("#signin-app-code-input", "short"); pg.click(APPBTN)
        self.assertIn("16", self.err(pg)); self.assertFalse(self.signed_in(pg))

    def test_3_rejected_app_password_stays_on_sign_in(self):
        pg = self.page()
        with mock.patch("live.user_data_backend.verify_gmail_login", return_value=(False, "Gmail rejected this email/App Password.")):
            pg.fill("#signin-email-input", "a@gmail.com"); pg.fill("#signin-app-code-input", "abcd efgh ijkl mnop"); pg.click(APPBTN)
            self.assertIn("rejected", self.err(pg))
        self.assertFalse(self.signed_in(pg))

    def test_4_accepted_app_password_signs_in_and_forgets_password(self):
        pg = self.page()
        with mock.patch("live.user_data_backend.verify_gmail_login", return_value=(True, None)):
            pg.fill("#signin-email-input", "me@gmail.com"); pg.fill("#signin-app-code-input", "abcd efgh ijkl mnop"); pg.click(APPBTN)
            pg.wait_for_function("document.getElementById('view-signin').classList.contains('hidden')", timeout=8000)
        self.assertEqual(pg.evaluate("currentProfile.email"), "me@gmail.com")
        self.assertEqual(pg.evaluate("currentProfile.appCode"), "")
        self.assertEqual(pg.input_value("#signin-app-code-input"), "")
        self.assertIn("App Password", pg.inner_text("#header-auth-badge"))

    def test_5_google_button_signs_in_with_verified_identity(self):
        pg = None
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "cid.apps.googleusercontent.com"}), \
             mock.patch("live.user_data_backend.verify_google_id_token", return_value=({"email": "Real@Gmail.com", "name": "Real Person"}, None)) as vg:
            pg = self.page()
            self.assertEqual(pg.evaluate("window.__gcid"), "cid.apps.googleusercontent.com")
            pg.click("#fake-g")
            pg.wait_for_function("document.getElementById('view-signin').classList.contains('hidden')", timeout=8000)
            self.assertEqual(vg.call_args[0][0], "fake-id-token")           # the real credential reached the verifier
        self.assertEqual(pg.evaluate("currentProfile.email"), "real@gmail.com")
        self.assertEqual(pg.evaluate("currentProfile.name"), "Real Person")
        self.assertIn("Google", pg.inner_text("#header-auth-badge"))

    def test_6_google_token_rejected(self):
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "cid"}), \
             mock.patch("live.user_data_backend.verify_google_id_token", return_value=(None, "Token audience does not match GOOGLE_CLIENT_ID.")):
            pg = self.page(); pg.click("#fake-g")
            self.assertIn("audience", self.err(pg))
        self.assertFalse(self.signed_in(pg))

    def test_7_saved_credentials_button_needs_real_saved_credentials(self):
        pg = self.page()
        pg.click("text=Use credentials saved"); self.assertIn("No saved Gmail credentials", self.err(pg)); self.assertFalse(self.signed_in(pg))

    def test_8_sign_out_revokes_session(self):
        from live import user_data_backend as udb
        pg = self.page()
        with mock.patch("live.user_data_backend.verify_gmail_login", return_value=(True, None)):
            pg.fill("#signin-email-input", "out@gmail.com"); pg.fill("#signin-app-code-input", "abcdefghijklmnop"); pg.click(APPBTN)
            pg.wait_for_function("document.getElementById('view-signin').classList.contains('hidden')", timeout=8000)
        before = udb.get_user_data_stats()["active_sessions"]
        pg.evaluate("signOutUser()")
        pg.wait_for_function("!document.getElementById('view-signin').classList.contains('hidden')", timeout=8000)
        time.sleep(0.3)
        self.assertEqual(udb.get_user_data_stats()["active_sessions"], before - 1)

    def test_9_backend_down_gives_actionable_message(self):
        pg = self.page()
        pg.evaluate("document.getElementById('vault-backend-url-input').value='http://127.0.0.1:9'")
        pg.fill("#signin-email-input", "a@gmail.com"); pg.fill("#signin-app-code-input", "abcdefghijklmnop"); pg.click(APPBTN)
        self.assertIn("Cannot reach the backend", self.err(pg)); self.assertFalse(self.signed_in(pg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
