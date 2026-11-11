import json, tempfile, unittest
from live.vault import VaultAgent, IntegrityError, PermissionDenied, LIVE_AGENT
from live.profile import split_private


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.v = VaultAgent(vault_dir=self.d, audit_path=self.d + "/audit.log")

    def test_roundtrip_and_text_files(self):
        self.v.save_artifact("a.json", {"k": 1}); self.assertEqual(self.v.load_artifact("a.json"), {"k": 1})
        ics = "BEGIN:VCALENDAR\nEND:VCALENDAR"; self.v.save_artifact("plan.ics", ics, "text/calendar")
        self.assertEqual(self.v.load_artifact("plan.ics"), ics)          # non-JSON files load as text

    def test_sha256_is_verified(self):
        self.v.save_artifact("a.json", {"k": 1})
        (self.v.dir / "a.json").write_text(json.dumps({"k": 2}))
        with self.assertRaises(IntegrityError): self.v.load_artifact("a.json")

    def test_version_increments(self):
        self.v.save_artifact("a.json", 1); self.v.save_artifact("a.json", 2)
        self.assertEqual(self.v._manifest()["a.json"]["version"], 2)

    def test_permissions_and_bad_names(self):
        with self.assertRaises(PermissionDenied): self.v.save_artifact("other.json", {}, agent_name=LIVE_AGENT)
        for bad in ("../x.json", ".hidden", "_manifest.json"):
            with self.assertRaises(ValueError): self.v.save_artifact(bad, {})

    def test_audit_log_appends(self):
        self.v.audit("submit_click", job="x"); self.v.audit("dry_run_fill", job="y")
        self.assertEqual(len((self.v.audit_path).read_text().splitlines()), 2)

    def test_bootstrap_has_no_private_fields(self):
        self.v.bootstrap_defaults_if_empty(); _, priv = split_private(self.v.load_artifact("user_profile_v1.json"))
        self.assertEqual(priv, {})
