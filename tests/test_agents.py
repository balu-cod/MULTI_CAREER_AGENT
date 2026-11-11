import datetime as dt, os, tempfile, unittest
from unittest import mock
from live import runtime
from live.vault import VaultAgent
from live.agents import _age_days, Matcher, Inbox, Funnel, FollowUp, AutoApply

AG = "LIVE_PIPELINE_AGENT"


def mk():
    v = VaultAgent(vault_dir=tempfile.mkdtemp()); v.bootstrap_defaults_if_empty(); runtime.discover(); return v

def ctx_for(v, **kw): return {"vault": v, "profile": v.load_artifact("user_profile_v1.json"), "log": lambda m: None, "insights": {}, **kw}

def job(**kw): return dict(dict(id="j1", portal="greenhouse", company="Acme", title="Python Intern", location="Remote", url="u", desc="python sql", posted=None), **kw)


class MatcherTests(unittest.TestCase):
    def test_staffing_is_not_staff(self):
        c = ctx_for(mk(), jobs=[job(title="Python Developer Intern, Staffing Platform", desc="python sql fastapi react")])
        Matcher().run(c); self.assertNotEqual(c["jobs"][0]["status"], "excluded_senior")

    def test_real_senior_titles_excluded(self):
        for t in ("Staff Engineer", "Sr. Python Developer", "Head of Engineering", "Senior Developer"):
            c = ctx_for(mk(), jobs=[job(title=t)]); Matcher().run(c); self.assertEqual(c["jobs"][0]["status"], "excluded_senior", t)

    def test_duplicates_and_pay(self):
        j = job(desc="python sql INR 20,000 - 30,000 /month"); c = ctx_for(mk(), jobs=[j, dict(j, id="j2")])
        Matcher().run(c); self.assertEqual(sum(x["status"] == "duplicate" for x in c["jobs"]), 1)
        self.assertIn("INR 20,000", c["matches"][0]["pay"] if c["matches"] else c["jobs"][0]["pay"])


class AgeTests(unittest.TestCase):
    def test_formats(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.assertEqual(_age_days((now - dt.timedelta(days=5)).timestamp() * 1000), 5)           # Lever epoch ms
        self.assertEqual(_age_days((now - dt.timedelta(days=5)).isoformat().replace("+00:00", "Z")), 5)
        self.assertEqual(_age_days((now - dt.timedelta(days=5)).replace(tzinfo=None).isoformat()), 5)   # naive = UTC
        self.assertIsNone(_age_days(None)); self.assertIsNone(_age_days("garbage"))


class InboxTests(unittest.TestCase):
    def run_inbox(self, apps, mails):
        v = mk(); v.save_artifact("live_applications_v1.json", apps, "application/json", [], "T", [], [], agent_name=AG)
        class M:
            def __init__(s, *a): pass
            def login(s, *a): pass
            def select(s, *a, **k): pass
            def search(s, *a): return "OK", [" ".join(str(i + 1) for i in range(len(mails))).encode()]
            def fetch(s, i, q): return "OK", [(b"x", mails[int(i) - 1].encode()), b")"]
            def logout(s): pass
        with mock.patch("imaplib.IMAP4_SSL", M), mock.patch.dict(os.environ, {"GMAIL_SMTP_USER": "u", "GMAIL_SMTP_APP_PASSWORD": "p"}):
            c = ctx_for(v); Inbox().run(c); Funnel().run(c)
        return v.load_artifact("live_applications_v1.json"), c

    def at(self): return dt.datetime.now().isoformat(timespec="seconds")

    def test_status_updates_and_rejection_overrides_interview(self):
        apps = {"a": {"company": "Acme", "title": "Dev", "status": "interview", "at": self.at()}, "b": {"company": "Zeta", "title": "Dev", "status": "applied", "at": self.at()}}
        mails = ["From: hr@acme.com\r\nSubject: Acme update\r\n\r\nUnfortunately we are not moving forward.",
                 "From: jobs@zeta.io\r\nSubject: Zeta interview\r\n\r\nWe would like to schedule a call."]
        out, c = self.run_inbox(apps, mails)
        self.assertEqual((out["a"]["status"], out["b"]["status"]), ("rejected", "interview"))
        self.assertEqual(c["insights"]["funnel"]["reply_rate"], 100)

    def test_body_only_mention_is_ignored_and_availability_is_not_interview(self):
        apps = {"a": {"company": "Acme", "title": "Dev", "status": "applied", "at": self.at()}}
        mails = ["From: news@random.com\r\nSubject: Newsletter\r\n\r\nWe met Acme at a conference. Unfortunately it rained.",
                 "From: hr@acme.com\r\nSubject: Acme: your application\r\n\r\nPlease confirm availability for onboarding forms."]
        out, _ = self.run_inbox(apps, mails); self.assertEqual(out["a"]["status"], "replied")


class FollowUpTests(unittest.TestCase):
    def test_day7_day14_then_stop(self):
        v = mk(); applied = lambda d: (dt.datetime.now() - dt.timedelta(days=d)).isoformat(timespec="seconds")
        v.save_artifact("live_applications_v1.json", {"a": {"company": "A", "title": "T", "status": "applied", "at": applied(8)}}, "application/json", [], "T", [], [], agent_name=AG)
        def run():
            c = ctx_for(v); FollowUp().run(c); return c["insights"]["followups_due"]
        self.assertEqual(len(run()), 1); self.assertEqual(run(), [])                      # day 7 sent once, not repeated
        apps = v.load_artifact("live_applications_v1.json"); apps["a"]["at"] = applied(15); v.save_artifact("live_applications_v1.json", apps)
        self.assertEqual(len(run()), 1); self.assertEqual(run(), [])                      # day 14 nudge, then stop
        apps = v.load_artifact("live_applications_v1.json"); apps["a"]["at"] = applied(40); v.save_artifact("live_applications_v1.json", apps)
        self.assertEqual(run(), [])


class AutoApplyGuards(unittest.TestCase):
    def test_off_and_unconfirmed_submit(self):
        v = mk()
        for env, expect in (({"APPLY_MODE": "off"}, "off"), ({"APPLY_MODE": "submit"}, "refused")):
            with mock.patch.dict(os.environ, env, clear=False):
                os.environ.pop("APPLY_CONFIRM", None); c = ctx_for(v); AutoApply().run(c); self.assertIn(expect, c["insights"]["autoapply"])
