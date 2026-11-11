"""The one VaultAgent: atomic writes, SHA-256 verified loads, per-agent allowlist, audit log."""
import datetime as dt, hashlib, json, os, pathlib, tempfile
from .profile import DEFAULT_PROFILE, DEFAULT_ROADMAP

LIVE_AGENT = "LIVE_PIPELINE_AGENT"
# Files each named agent may touch. LIVE_PIPELINE_AGENT may use any live_* / ai_* artifact plus the core profile files.
PERMISSIONS = {
    LIVE_AGENT: {"user_profile_v1.json", "skill_roadmap_v1.json", "live_results_v1.json", "live_applications_v1.json", "ai_updates_v1.json", "youtube_updates_v1.json", "contests_v1.json", "evening_review_v1.json", "user_personalization_memory.json"},
}
MANIFEST = "_manifest.json"


class IntegrityError(RuntimeError):
    pass


class PermissionDenied(PermissionError):
    pass


class VaultAgent:
    def __init__(self, vault_dir="vault", audit_path=None):
        self.dir = pathlib.Path(vault_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir = str(self.dir)
        self.audit_path = pathlib.Path(audit_path) if audit_path else self.dir.parent / "private" / "audit.log"

    # ---- helpers
    def _check(self, filename, agent_name):
        if agent_name is None:
            return
        if filename not in PERMISSIONS.get(agent_name, set()):
            raise PermissionDenied(f"{agent_name} may not access {filename}")

    def _manifest(self):
        p = self.dir / MANIFEST
        try:
            return json.loads(p.read_text("utf-8")) if p.exists() else {}
        except json.JSONDecodeError:
            return {}

    def _atomic_write(self, path, data: bytes):
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data); f.flush()
                try: os.fsync(f.fileno())
                except OSError: pass
            try:
                os.replace(tmp, path)
            except OSError:
                path.write_bytes(data)
                if os.path.exists(tmp): os.unlink(tmp)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def audit(self, action, **details):
        """Append-only record of sensitive actions (apply, submit, save). Stored in private/, never committed."""
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "action": action, **details}
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---- API
    def save_artifact(self, filename, content, mime="application/json", tags=None, owner=None, skills=None, access=None, agent_name=None):
        self._check(filename, agent_name)
        if "/" in filename or "\\" in filename or filename.startswith(".") or filename == MANIFEST:
            raise ValueError(f"bad artifact name: {filename!r}")
        data = (json.dumps(content, indent=2, ensure_ascii=False) if filename.endswith(".json") else str(content)).encode("utf-8")
        self._atomic_write(self.dir / filename, data)
        man = self._manifest(); prev = man.get(filename, {})
        man[filename] = {"sha256": hashlib.sha256(data).hexdigest(), "version": prev.get("version", 0) + 1, "mime": mime, "tags": tags or [],
                         "owner": owner, "skills": skills or [], "access": access or [], "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        self._atomic_write(self.dir / MANIFEST, json.dumps(man, indent=2).encode("utf-8"))
        return str(self.dir / filename)

    def load_artifact(self, filename, agent_name=None):
        self._check(filename, agent_name)
        path = self.dir / filename
        if not path.exists():
            return None
        data = path.read_bytes()
        rec = self._manifest().get(filename)
        if rec and hashlib.sha256(data).hexdigest() != rec["sha256"]:
            raise IntegrityError(f"{filename} does not match its recorded SHA-256 (edited outside the Vault?)")
        text = data.decode("utf-8")
        return json.loads(text) if filename.endswith(".json") else text   # .ics / .html / .md come back as text

    def bootstrap_defaults_if_empty(self):
        made = {}
        for name, default in (("user_profile_v1.json", DEFAULT_PROFILE), ("skill_roadmap_v1.json", DEFAULT_ROADMAP)):
            if not (self.dir / name).exists():
                self.save_artifact(name, default, tags=["default"], owner="SYSTEM"); made[name] = "created"
        return made
