"""
accounts.py — Owner / session / OAuth-token management for the full OAuth 2.0 flow.

Sits on top of the existing user_data_backend SQLite database and adds:
  - oauth_tokens table  (access + refresh tokens, expiry, scopes)
  - sessions table with idle_expires_at / abs_expires_at / revoked  (richer than the
    existing oauth_sessions table which the GSI / App-Password path still uses)

The two session tables coexist; the new PKCE flow uses `sessions` exclusively.
"""
import datetime as dt, hashlib, json, os, secrets, sqlite3
from typing import Optional, Tuple

from . import user_data_backend as udb

# ---------------------------------------------------------------- helpers
_LOCK = udb._LOCK       # share the same DB lock


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t=None) -> str:
    return (t or _now()).isoformat(timespec="seconds")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- schema additions

ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash       TEXT UNIQUE NOT NULL,
    email            TEXT NOT NULL,
    name             TEXT DEFAULT '',
    picture          TEXT DEFAULT '',
    provider         TEXT NOT NULL DEFAULT 'google_oauth2',
    created_at       TEXT NOT NULL,
    idle_expires_at  TEXT NOT NULL,
    abs_expires_at   TEXT NOT NULL,
    revoked          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_hash ON sessions(token_hash);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    email              TEXT PRIMARY KEY,
    access_token       TEXT NOT NULL DEFAULT '',
    refresh_token      TEXT NOT NULL DEFAULT '',
    access_expires_at  TEXT NOT NULL DEFAULT '2000-01-01T00:00:00+00:00',
    scopes             TEXT NOT NULL DEFAULT '[]',
    needs_reauth       INTEGER NOT NULL DEFAULT 0,
    updated_at         TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    con = udb._connect()
    con.executescript(ACCOUNTS_SCHEMA)
    return con


# ---------------------------------------------------------------- owner

OWNER_KEY = "owner_email"


def owner_email() -> str:
    """Return the pinned owner email, or ''."""
    with _LOCK, _connect() as con:
        row = con.execute("SELECT value FROM kv WHERE key=?", (OWNER_KEY,)).fetchone()
        return (row[0] if row else "") or ""


def set_owner(email: str) -> None:
    with _LOCK, _connect() as con:
        con.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (OWNER_KEY, email.lower()))


def reset_owner() -> None:
    """Clear the owner pin and revoke all active sessions."""
    with _LOCK, _connect() as con:
        con.execute("DELETE FROM kv WHERE key=?", (OWNER_KEY,))
        con.execute("UPDATE sessions SET revoked=1")
        con.execute("UPDATE oauth_sessions SET revoked=1")  # legacy table too


def _ensure_kv(con):
    """Create kv table if the DB was initialised before accounts.py existed."""
    con.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')")


# ---------------------------------------------------------------- sessions (new PKCE flow)

def _idle_hours() -> float:
    try:
        return float(os.environ.get("SESSION_IDLE_HOURS") or 12)
    except ValueError:
        return 12.0


def _max_days() -> float:
    try:
        return float(os.environ.get("SESSION_MAX_DAYS") or 7)
    except ValueError:
        return 7.0


def create_session(email: str, name: str = "", picture: str = "") -> Tuple[str, str]:
    """
    Create a new PKCE-flow session.  Returns (token, abs_expires_at_iso).
    Also revokes any pre-existing live sessions for the same email (session fixation).
    """
    token = secrets.token_urlsafe(32)
    now   = _now()
    idle  = now + dt.timedelta(hours=_idle_hours())
    abso  = now + dt.timedelta(days=_max_days())
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        # revoke existing live sessions for this email (prevents fixation)
        con.execute("UPDATE sessions SET revoked=1 WHERE email=? AND revoked=0", (email.lower(),))
        con.execute(
            "INSERT INTO sessions (token_hash,email,name,picture,provider,created_at,idle_expires_at,abs_expires_at) VALUES (?,?,?,?,'google_oauth2',?,?,?)",
            (_hash(token), email.lower(), name, picture, _iso(now), _iso(idle), _iso(abso)),
        )
    return token, _iso(abso)


def session_from_token(token: str) -> Optional[dict]:
    if not token:
        return None
    now = _iso()
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        row = con.execute(
            "SELECT * FROM sessions WHERE token_hash=? AND revoked=0 AND idle_expires_at>? AND abs_expires_at>?",
            (_hash(token), now, now),
        ).fetchone()
        if row:
            # slide idle window
            new_idle = _iso(_now() + dt.timedelta(hours=_idle_hours()))
            con.execute("UPDATE sessions SET idle_expires_at=? WHERE token_hash=?", (new_idle, _hash(token)))
        return dict(row) if row else None


def revoke_session(token: str) -> None:
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        con.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (_hash(token),))


# ---------------------------------------------------------------- OAuth tokens

def save_tokens(email: str, access_token: str, refresh_token: str,
                expires_in: int, scopes: list) -> None:
    exp = _iso(_now() + dt.timedelta(seconds=max(0, expires_in - 30)))
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        existing = con.execute("SELECT refresh_token FROM oauth_tokens WHERE email=?", (email.lower(),)).fetchone()
        # keep old refresh_token if the new one is absent (Google sometimes omits it on re-auth)
        rt = refresh_token or (existing[0] if existing else "")
        con.execute(
            "INSERT OR REPLACE INTO oauth_tokens (email,access_token,refresh_token,access_expires_at,scopes,needs_reauth,updated_at) VALUES (?,?,?,?,?,0,?)",
            (email.lower(), access_token, rt, exp, json.dumps(scopes), _iso()),
        )


def get_tokens(email: str) -> Optional[dict]:
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        row = con.execute("SELECT * FROM oauth_tokens WHERE email=?", (email.lower(),)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["scopes"] = json.loads(d.get("scopes") or "[]")
        return d


def fresh_access_token(email: str) -> Optional[str]:
    """
    Return a valid access token, refreshing if expired.
    Returns None if no tokens exist or refresh fails.
    """
    tokens = get_tokens(email)
    if not tokens:
        return None
    if tokens.get("needs_reauth"):
        return None

    exp = tokens.get("access_expires_at", "")
    try:
        exp_dt = dt.datetime.fromisoformat(exp)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=dt.timezone.utc)
    except Exception:
        exp_dt = _now() - dt.timedelta(seconds=1)   # treat as expired

    if _now() < exp_dt:
        return tokens["access_token"]

    # expired — refresh
    rt = tokens.get("refresh_token", "")
    if not rt:
        return None
    try:
        from .oauth_google import refresh_access_token, OAuthError
        resp = refresh_access_token(rt)
        at   = resp.get("access_token", "")
        ei   = int(resp.get("expires_in", 3600))
        new_rt = resp.get("refresh_token", rt)
        scopes = get_tokens(email)["scopes"]  # keep existing scopes
        save_tokens(email, at, new_rt, ei, scopes)
        return at
    except Exception:
        return None


def invalidate_access_token(email: str) -> None:
    """Force expiry of the cached access token so the next call triggers a refresh."""
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        con.execute(
            "UPDATE oauth_tokens SET access_expires_at='2000-01-01T00:00:00+00:00' WHERE email=?",
            (email.lower(),),
        )


def mark_needs_reauth(email: str) -> None:
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        con.execute("UPDATE oauth_tokens SET needs_reauth=1 WHERE email=?", (email.lower(),))


def delete_tokens(email: str) -> None:
    with _LOCK, _connect() as con:
        _ensure_kv(con)
        con.execute("DELETE FROM oauth_tokens WHERE email=?", (email.lower(),))
