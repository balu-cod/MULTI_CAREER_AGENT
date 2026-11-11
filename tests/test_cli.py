import json, pathlib, tempfile, unittest
from unittest import mock
import career_agent_system as cli
from live.vault import VaultAgent


class CliTests(unittest.TestCase):
    def test_scrub_private_moves_contact_details(self):
        d = tempfile.mkdtemp()
        root = pathlib.Path(tempfile.mkdtemp())
        v = VaultAgent(vault_dir=d)
        v.save_artifact("user_profile_v1.json", {"handle": "h", "contact_phone": "123", "contact_email": "a@b.c", "education": "X roll 1"})
        with mock.patch.object(cli, "ROOT", root):
            cli.scrub_private(v, lambda m: None)
        self.assertEqual(v.load_artifact("user_profile_v1.json"), {"handle": "h"})
        self.assertEqual(json.loads((root / "private" / "profile.json").read_text())["contact_phone"], "123")

    def test_env_folder_loader_and_aliases(self):
        import os
        from live.env_loader import ensure_env_folder, set_secret, read_env_folder_values, load_env, env_status
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            env_dir = ensure_env_folder(root)
            self.assertTrue((env_dir / "secrets.env").is_file())
            self.assertTrue((env_dir / "keys.json").is_file())
            self.assertTrue((env_dir / "secrets.env.example").is_file())
            self.assertTrue((env_dir / "README.md").is_file())
            with mock.patch.dict(os.environ, {}, clear=False):
                set_secret("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop", root=root)
                vals = read_env_folder_values(root)
                self.assertEqual(vals["GMAIL_APP_PASSWORD"], "abcdefghijklmnop")
                self.assertEqual(vals["GMAIL_SMTP_APP_PASSWORD"], "abcdefghijklmnop")
                (env_dir / "GEMINI_API_KEY").write_text("AIzaSyTestKey123456\n", "utf-8")
                vals2 = read_env_folder_values(root)
                self.assertEqual(vals2["GEMINI_API_KEY"], "AIzaSyTestKey123456")
                os.environ.pop("GEMINI_API_KEY", None)
                load_env(root=root, override=True)
                self.assertEqual(os.environ.get("GEMINI_API_KEY"), "AIzaSyTestKey123456")
                st = env_status(root=root)
                gem_row = next(r for r in st["keys"] if r["key"] == "GEMINI_API_KEY")
                self.assertEqual(gem_row["status"], "READY")
                self.assertIn("...", gem_row["masked"])

    def test_fetch_keys_from_gmail_imap(self):
        import email.message, os
        from live.env_loader import ensure_env_folder, set_secret, fetch_keys_from_gmail, read_env_folder_values
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            ensure_env_folder(root)
            set_secret("GMAIL_ADDRESS", "you@example.com", root=root)
            set_secret("GMAIL_APP_PASSWORD", "abcdefghijklmnop", root=root)
            msg = email.message.EmailMessage()
            msg["Subject"] = "CAREER_AGENT_KEYS YouTube and GitHub"
            msg.set_content("GEMINI_API_KEY=AIzaSyDummyKeyForTesting123456789012345\nGITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwx12\nGROQ_API_KEY=gsk_1234567890abcdefghijklmnopqrstuvwxyz12345678\n")
            raw_bytes = msg.as_bytes()

            class FakeIMAP:
                def __init__(self, host): pass
                def login(self, u, p): pass
                def select(self, box, readonly=True): pass
                def search(self, charset, crit): return ("OK", [b"1"])
                def fetch(self, mid, parts): return ("OK", [(b"1", raw_bytes)])
                def logout(self): pass

            with mock.patch("imaplib.IMAP4_SSL", FakeIMAP), mock.patch.dict(os.environ, {}, clear=False):
                found = fetch_keys_from_gmail(root=root, log=lambda m: None)
                self.assertIn("GEMINI_API_KEY", found)
                self.assertIn("GITHUB_TOKEN", found)
                self.assertIn("GROQ_API_KEY", found)
                vals = read_env_folder_values(root)
                self.assertEqual(vals["GITHUB_TOKEN"], "ghp_1234567890abcdefghijklmnopqrstuvwx12")

    def test_local_server_api_and_contests_agent(self):
        from live import runtime
        from live.server import build_api_status, handle_api_post
        from live.agents import Contests, EveningReview
        runtime.discover()
        d = tempfile.mkdtemp()
        v = VaultAgent(vault_dir=d)
        v.bootstrap_defaults_if_empty()
        ctx = {"vault": v, "profile": {"technical_skills": ["Python", "SQL", "FastAPI"]}, "log": lambda m: None, "insights": {}}
        fake_unstop = {
            "data": {
                "data": [
                    {
                        "id": 101,
                        "title": "Build with AI Hackathon",
                        "organisation": {"name": "Unstop"},
                        "seo_url": "hackathons/build-with-ai-101",
                        "skills": ["Python", "FastAPI"],
                        "prizes": [{"cash": 50000}],
                    }
                ]
            }
        }
        fake_devpost = {
            "hackathons": [
                {
                    "id": 202,
                    "title": "Global Agentic AI Challenge",
                    "organization_name": "Devpost",
                    "url": "https://devpost.com/hackathons/global-agentic-ai",
                    "prize_amount": "$10,000",
                    "themes": [{"name": "Python"}, {"name": "AI"}],
                }
            ]
        }
        with mock.patch.dict(runtime.TOOLS, {"get_json": lambda u: fake_unstop if "unstop.com" in u else fake_devpost}):
            Contests().run(ctx)
        saved_contests = v.load_artifact("contests_v1.json")
        self.assertEqual(len(saved_contests.get("contests", [])), 2)
        st = build_api_status(v)
        self.assertTrue(st["ok"])
        self.assertIn("contests", st)
        res_resume = handle_api_post("/api/resume", {"job": "Python FastAPI Backend Intern with SQL and Docker"}, v, log=lambda m: None)
        self.assertTrue(res_resume["ok"])
        self.assertEqual(res_resume["pages"], 1)
        ctx["matches"] = []
        EveningReview().run(ctx)
        ev = v.load_artifact("evening_review_v1.json")
        self.assertIn("tonight_study", ev)
