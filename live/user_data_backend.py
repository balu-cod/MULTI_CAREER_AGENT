"""User Data Backend: SQLite store (private/user_data.db), Google OAuth 2.0 sign-in, Gmail IMAP sync.

Public API used by live/server.py and career_agent_system.py:
    handle_user_data_request(path, payload, method="POST", headers=None) -> dict
    get_user_data_stats() -> dict
    update_candidate_profile(fields) -> dict
    save_user_application(app) -> dict
    serve_user_backend(port=8001, host="127.0.0.1", log=print)

Security model
- Google ID tokens are verified against Google's tokeninfo endpoint: audience must equal GOOGLE_CLIENT_ID,
  issuer must be Google, token not expired, email_verified true. No client id configured = sign-in refused,
  unless USERDATA_DEV_AUTH=1 (local development only; the session is flagged dev=true).
- Only a SHA-256 hash of the session token is stored. Tokens expire (default 12h, USERDATA_SESSION_HOURS).
- Set USERDATA_REQUIRE_AUTH=1 to require `Authorization: Bearer <session>` on every /api/userdata call.
- Gmail App Passwords are never written to the database; credentials come from the request or .env/.
"""
import datetime as dt, email as email_lib, email.header, email.utils, hashlib, imaplib, json, os, pathlib, re, secrets, sqlite3, threading, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_NAME = "user_data.db"
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    full_name TEXT, email TEXT, phone TEXT, location TEXT, extra_json TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS oauth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT UNIQUE NOT NULL, email TEXT NOT NULL, name TEXT, picture TEXT,
    provider TEXT NOT NULL DEFAULT 'google', dev INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS gmail_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL, message_id TEXT NOT NULL, sender TEXT, sender_email TEXT, subject TEXT,
    snippet TEXT, received_at TEXT, folder TEXT DEFAULT 'INBOX', synced_at TEXT,
    UNIQUE (owner, message_id)
);
CREATE TABLE IF NOT EXISTS contacts (
    email TEXT PRIMARY KEY, name TEXT, company TEXT, source TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY, job_title TEXT, company TEXT, hiring_email TEXT, source_portal TEXT,
    status TEXT, ats_score REAL, resume_path TEXT, outreach_note TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    status TEXT DEFAULT 'SUCCESS',
    actor TEXT DEFAULT 'SYSTEM'
);
CREATE INDEX IF NOT EXISTS idx_gmail_owner_date ON gmail_messages(owner, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_exp ON oauth_sessions(expires_at);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_ledger_date ON audit_ledger(date DESC, timestamp DESC);
"""


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _iso(t=None):
    return (t or _now()).isoformat(timespec="seconds")


def db_path():
    return pathlib.Path(os.environ.get("USERDATA_DB") or (ROOT / "private" / DB_NAME))


def _connect():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA synchronous=OFF")
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return con


def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


# ---------------------------------------------------------------- profile

PROFILE_FIELDS = ("full_name", "email", "phone", "location")


def update_candidate_profile(fields):
    fields = fields or {}
    email = str(fields.get("email") or "").strip()
    if email and not EMAIL_RE.match(email):
        return {"ok": False, "error": "Invalid email address."}
    with _LOCK, _connect() as con:
        cur = con.execute("SELECT * FROM candidate_profile WHERE id=1").fetchone()
        cur = dict(cur) if cur else {}
        extra = json.loads(cur.get("extra_json") or "{}")
        vals = {k: cur.get(k) for k in PROFILE_FIELDS}
        for k, v in fields.items():
            if k in PROFILE_FIELDS:
                vals[k] = str(v).strip()[:300] if v is not None else None
            elif k not in ("password", "app_password", "credential", "token"):
                extra[str(k)[:60]] = v
        con.execute(
            "INSERT INTO candidate_profile (id, full_name, email, phone, location, extra_json, updated_at) VALUES (1,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name, email=excluded.email, phone=excluded.phone, "
            "location=excluded.location, extra_json=excluded.extra_json, updated_at=excluded.updated_at",
            (vals["full_name"], vals["email"], vals["phone"], vals["location"], json.dumps(extra), _iso()),
        )
    return {"ok": True, "profile": {**vals, **extra}}


def get_candidate_profile():
    with _LOCK, _connect() as con:
        r = con.execute("SELECT * FROM candidate_profile WHERE id=1").fetchone()
    if not r:
        return {}
    r = dict(r)
    extra = json.loads(r.pop("extra_json") or "{}")
    return {**{k: r.get(k) for k in PROFILE_FIELDS}, **extra, "updated_at": r.get("updated_at")}


# ---------------------------------------------------------------- applications

def save_user_application(app):
    app = app or {}
    app_id = str(app.get("id") or f"app-{int(_now().timestamp())}")
    with _LOCK, _connect() as con:
        con.execute(
            "INSERT INTO applications (id, job_title, company, hiring_email, source_portal, status, ats_score, resume_path, outreach_note, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET job_title=excluded.job_title, company=excluded.company, "
            "hiring_email=excluded.hiring_email, source_portal=excluded.source_portal, status=excluded.status, ats_score=excluded.ats_score, "
            "resume_path=excluded.resume_path, outreach_note=excluded.outreach_note, updated_at=excluded.updated_at",
            (
                app_id, str(app.get("job_title") or app.get("title") or ""), str(app.get("company") or ""),
                str(app.get("hiring_email") or ""), str(app.get("source_portal") or ""), str(app.get("status") or "Applied"),
                app.get("ats_score"), str(app.get("resume_path") or ""), str(app.get("outreach_note") or ""), _iso(), _iso(),
            ),
        )
        he = str(app.get("hiring_email") or "").strip()
        if EMAIL_RE.match(he):
            _upsert_contact(con, he, "", str(app.get("company") or ""), "application")
    return {"ok": True, "id": app_id}


def _upsert_contact(con, addr, name, company, source, phone="", notes=""):
    try:
        con.execute("ALTER TABLE contacts ADD COLUMN phone TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE contacts ADD COLUMN notes TEXT DEFAULT ''")
    except Exception:
        pass
    con.execute(
        "INSERT INTO contacts (email, name, company, source, last_seen, phone, notes) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(email) DO UPDATE SET name=COALESCE(NULLIF(excluded.name,''), contacts.name), "
        "company=COALESCE(NULLIF(excluded.company,''), contacts.company), "
        "phone=COALESCE(NULLIF(excluded.phone,''), contacts.phone), "
        "notes=COALESCE(NULLIF(excluded.notes,''), contacts.notes), "
        "last_seen=excluded.last_seen",
        (addr.lower(), name, company, source, _iso(), str(phone or ""), str(notes or "")),
    )


def save_hiring_contact(payload):
    payload = payload or {}
    email = str(payload.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Valid corporate email address is required."}
    name = str(payload.get("name") or "Hiring Team").strip()
    company = str(payload.get("company") or "Organization").strip()
    phone = str(payload.get("phone") or "").strip()
    notes = str(payload.get("notes") or "Verified hiring contact").strip()
    source = str(payload.get("source") or "manual").strip()
    with _LOCK, _connect() as con:
        _upsert_contact(con, email, name, company, source, phone=phone, notes=notes)
        contacts = _rows(con, "SELECT * FROM contacts ORDER BY last_seen DESC LIMIT 500")
    record_ledger_action("USER_DATA", "SAVE_CONTACT", f"Saved contact {name} ({email}) at {company}", actor="USER")
    return {"ok": True, "email": email, "contacts": contacts}


def delete_hiring_contact(email):
    email = str(email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "Missing contact email."}
    with _LOCK, _connect() as con:
        con.execute("DELETE FROM contacts WHERE lower(email)=?", (email,))
        contacts = _rows(con, "SELECT * FROM contacts ORDER BY last_seen DESC LIMIT 500")
    record_ledger_action("USER_DATA", "DELETE_CONTACT", f"Removed contact {email}", actor="USER")
    return {"ok": True, "email": email, "contacts": contacts}


def delete_user_application(app_id):
    app_id = str(app_id or "").strip()
    if not app_id:
        return {"ok": False, "error": "Missing application id."}
    with _LOCK, _connect() as con:
        con.execute("DELETE FROM applications WHERE id=?", (app_id,))
    record_ledger_action("APPLICATION_TRACKED", "DELETE_APPLICATION", f"Removed application {app_id}", actor="USER")
    return {"ok": True, "id": app_id}


# ---------------------------------------------------------------- Google OAuth

def verify_google_id_token(credential, client_id=None, fetch=None):
    """Return (claims, error). `fetch(url)` -> dict is injectable for tests."""
    client_id = client_id or os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        return None, "GOOGLE_CLIENT_ID is not configured (set it with --set-key GOOGLE_CLIENT_ID=...)."
    if not credential or not isinstance(credential, str) or len(credential) > 4096:
        return None, "Missing Google ID token."
    try:
        if fetch:
            claims = fetch(f"{GOOGLE_TOKENINFO}?id_token={urllib.parse.quote(credential)}")
        else:
            with urllib.request.urlopen(f"{GOOGLE_TOKENINFO}?id_token={urllib.parse.quote(credential)}", timeout=10) as r:
                claims = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return None, "Google rejected the ID token."
    except Exception as e:
        return None, f"Could not reach Google to verify the token ({type(e).__name__})."
    if claims.get("aud") != client_id:
        return None, "Token audience does not match GOOGLE_CLIENT_ID."
    if claims.get("iss") not in GOOGLE_ISSUERS:
        return None, "Token issuer is not Google."
    try:
        if int(claims.get("exp", 0)) < int(_now().timestamp()):
            return None, "Token expired."
    except (TypeError, ValueError):
        return None, "Token has no valid expiry."
    if str(claims.get("email_verified")).lower() != "true":
        return None, "Google account email is not verified."
    if not EMAIL_RE.match(str(claims.get("email") or "")):
        return None, "Token has no email."
    return claims, None


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(email, name="", picture="", provider="google", dev=False):
    token = secrets.token_urlsafe(32)
    hours = float(os.environ.get("USERDATA_SESSION_HOURS", "12") or 12)
    exp = _now() + dt.timedelta(hours=hours)
    with _LOCK, _connect() as con:
        con.execute("DELETE FROM oauth_sessions WHERE expires_at < ?", (_iso(),))
        con.execute(
            "INSERT INTO oauth_sessions (token_hash, email, name, picture, provider, dev, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
            (_hash(token), email, name, picture, provider, 1 if dev else 0, _iso(), _iso(exp)),
        )
    return token, _iso(exp)


def session_from_token(token):
    if not token:
        return None
    with _LOCK, _connect() as con:
        r = con.execute("SELECT * FROM oauth_sessions WHERE token_hash=? AND revoked=0 AND expires_at > ?", (_hash(token), _iso())).fetchone()
    return dict(r) if r else None


def _bearer(headers):
    h = (headers or {}).get("Authorization") or (headers or {}).get("authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") else ""


def handle_google_auth(payload, fetch=None):
    credential = payload.get("credential")
    claims, err = verify_google_id_token(credential, fetch=fetch)
    dev = False
    if err:
        # Local development fallback only; never on by default.
        if os.environ.get("USERDATA_DEV_AUTH") == "1" and (not os.environ.get("GOOGLE_CLIENT_ID") or payload.get("dev_login") or not payload.get("credential")):
            addr = str(payload.get("email") or "").strip()
            if not EMAIL_RE.match(addr):
                return {"ok": False, "error": "Invalid email address."}
            claims, dev = {"email": addr, "name": str(payload.get("name") or ""), "picture": ""}, True
        else:
            return {"ok": False, "error": err}
    addr = claims["email"].lower()
    token, exp = create_session(addr, claims.get("name", ""), claims.get("picture", ""), dev=dev)
    cur = get_candidate_profile()
    upd = {"email": addr}
    if not cur.get("full_name") and claims.get("name"):
        upd["full_name"] = claims["name"]
    update_candidate_profile(upd)
    return {"ok": True, "email": addr, "name": claims.get("name", ""), "session_token": token, "expires_at": exp, "dev": dev}


# ---------------------------------------------------------------- sign-in helpers

APP_PASSWORD_RE = re.compile(r"^[A-Za-z0-9]{16}$")


def auth_config():
    """Public sign-in settings for the browser (the OAuth client id is not a secret)."""
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    return {"ok": True, "google_client_id": cid, "oauth_configured": bool(cid),
            "dev_auth": os.environ.get("USERDATA_DEV_AUTH") == "1" and not cid,
            "has_saved_gmail": bool((os.environ.get("GMAIL_ADDRESS") or os.environ.get("GMAIL_SMTP_USER")) and (os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_SMTP_APP_PASSWORD")))}


def verify_gmail_login(user, password, imap_factory=None):
    """Really log in to Gmail IMAP. Returns (ok, error_message)."""
    user = (user or "").strip(); password = (password or "").replace(" ", "")
    if not EMAIL_RE.match(user):
        return False, "Enter a valid Gmail address."
    if not APP_PASSWORD_RE.match(password):
        return False, "The App Password must be exactly 16 letters/digits (spaces are ignored)."
    try:
        M = (imap_factory or (lambda: imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)))()
        M.login(user, password)
        try:
            M.logout()
        except Exception:
            pass
        return True, None
    except imaplib.IMAP4.error:
        return False, "Gmail rejected this email/App Password. Use a 16-character App Password (not your normal password), with 2-Step Verification and IMAP turned on."
    except Exception as e:
        return False, f"Could not reach Gmail (imap.gmail.com:993) - check your internet/firewall ({type(e).__name__})."


# ---------------------------------------------------------------- Gmail IMAP sync

def _decode(v):
    try:
        return str(email.header.make_header(email.header.decode_header(v or "")))
    except Exception:
        return str(v or "")


def _snippet(msg, n=240):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace") if part.get_payload(decode=True) else ""
                break
    elif msg.get_content_type() == "text/plain":
        raw = msg.get_payload(decode=True)
        body = raw.decode(msg.get_content_charset() or "utf-8", "replace") if raw else ""
    return re.sub(r"\s+", " ", body).strip()[:n]


def sync_gmail(user=None, password=None, limit=50, imap_factory=None):
    user = (user or os.environ.get("GMAIL_ADDRESS") or os.environ.get("GMAIL_SMTP_USER") or "").strip()
    password = (password or os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_SMTP_APP_PASSWORD") or "").replace(" ", "")
    if not EMAIL_RE.match(user) or not password:
        return {"ok": False, "error": "Gmail address and App Password are required (request body or .env/)."}
    limit = max(1, min(int(limit or 50), 200))
    try:
        M = (imap_factory or (lambda: imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)))()
        M.login(user, password)
        M.select("INBOX", readonly=True)
        typ, data = M.search(None, "ALL")
        ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-limit:]
        stored = 0
        with _LOCK, _connect() as con:
            for i in reversed(ids):
                typ, md = M.fetch(i, "(BODY.PEEK[]<0.6000>)")
                if typ != "OK" or not md or not isinstance(md[0], tuple):
                    continue
                msg = email_lib.message_from_bytes(md[0][1])
                name, addr = email.utils.parseaddr(msg.get("From", ""))
                mid = (msg.get("Message-ID") or f"{user}-{i.decode() if isinstance(i, bytes) else i}").strip()
                try:
                    received = email.utils.parsedate_to_datetime(msg.get("Date")).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
                except Exception:
                    received = _iso()
                cur = con.execute(
                    "INSERT OR IGNORE INTO gmail_messages (owner, message_id, sender, sender_email, subject, snippet, received_at, synced_at) VALUES (?,?,?,?,?,?,?,?)",
                    (user.lower(), mid, _decode(name), addr.lower(), _decode(msg.get("Subject"))[:300], _snippet(msg), received, _iso()),
                )
                stored += cur.rowcount
                if EMAIL_RE.match(addr):
                    _upsert_contact(con, addr, _decode(name), "", "gmail")
        try:
            M.logout()
        except Exception:
            pass
    except imaplib.IMAP4.error:
        return {"ok": False, "error": "Gmail rejected the login. Use a 16-character App Password and enable IMAP."}
    except Exception as e:
        return {"ok": False, "error": f"Gmail sync failed ({type(e).__name__})."}
    with _LOCK, _connect() as con:
        total = con.execute("SELECT COUNT(*) FROM gmail_messages WHERE owner=?", (user.lower(),)).fetchone()[0]
    return {"ok": True, "new_messages": stored, "total_stored": total}


# ---------------------------------------------------------------- stats / export

def get_user_data_stats():
    p = db_path()
    with _LOCK, _connect() as con:
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("candidate_profile", "oauth_sessions", "gmail_messages", "contacts", "applications", "audit_ledger")}
        active = con.execute("SELECT COUNT(*) FROM oauth_sessions WHERE revoked=0 AND expires_at > ?", (_iso(),)).fetchone()[0]
    return {
        "ok": True,
        "database": {"path": "private/" + p.name, "size_kb": round(p.stat().st_size / 1024, 1) if p.exists() else 0},
        "tables": counts,
        "active_sessions": active,
        "oauth_configured": bool(os.environ.get("GOOGLE_CLIENT_ID")),
    }


def export_user_data(owner=None):
    with _LOCK, _connect() as con:
        return {
            "exported_at": _iso(),
            "candidate_profile": get_candidate_profile(),
            "gmail_messages": _rows(con, "SELECT sender, sender_email, subject, snippet, received_at FROM gmail_messages ORDER BY received_at DESC LIMIT 500"),
            "contacts": _rows(con, "SELECT * FROM contacts ORDER BY last_seen DESC"),
            "applications": _rows(con, "SELECT * FROM applications ORDER BY created_at DESC"),
        }



# ---------------------------------------------------------------- audit ledger

def record_ledger_action(category, action, details="", status="SUCCESS", actor="SYSTEM"):
    """Record an action into SQLite audit_ledger, private/audit.log, and vault/workflow_audit_log.json."""
    t = _now()
    ts = _iso(t)
    date_str = t.strftime("%Y-%m-%d")
    try:
        with _LOCK, _connect() as con:
            con.execute(
                "INSERT INTO audit_ledger (timestamp, date, category, action, details, status, actor) VALUES (?,?,?,?,?,?,?)",
                (ts, date_str, str(category).upper(), str(action).upper(), str(details)[:1000], str(status).upper(), str(actor)[:100])
            )
    except Exception:
        pass
    try:
        log_path = ROOT / "private" / "audit.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{category.upper()}] {action.upper()} - {details} (Status: {status}, Actor: {actor})\n")
    except Exception:
        pass
    try:
        wf_path = ROOT / "vault" / "workflow_audit_log.json"
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if wf_path.exists():
            try: existing = json.loads(wf_path.read_text("utf-8"))
            except Exception: existing = []
        if not isinstance(existing, list): existing = []
        existing.insert(0, {
            "timestamp": ts,
            "date": date_str,
            "category": str(category).upper(),
            "action": str(action).upper(),
            "details": str(details),
            "status": str(status).upper(),
            "actor": str(actor)
        })
        wf_path.write_text(json.dumps(existing[:200], indent=2), "utf-8")
    except Exception:
        pass
    return {"ok": True, "timestamp": ts, "date": date_str}


def get_ledger_entries(limit=100, date=None):
    """Retrieve date-stamped action entries from the persistent audit ledger."""
    try:
        with _LOCK, _connect() as con:
            if date:
                rows = con.execute("SELECT * FROM audit_ledger WHERE date=? ORDER BY timestamp DESC LIMIT ?", (date, limit)).fetchall()
            else:
                rows = con.execute("SELECT * FROM audit_ledger ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []

# ---------------------------------------------------------------- router

def handle_user_data_request(path, payload=None, method="POST", headers=None):
    payload = payload if isinstance(payload, dict) else {}
    method = method.upper()
    path = path.rstrip("/")
    try:
        if path == "/api/auth/config" and method == "GET":
            return auth_config()
        if path == "/api/auth/google" and method == "POST":
            return handle_google_auth(payload)
        if not path.startswith("/api/userdata"):
            return {"ok": False, "error": f"Unknown endpoint: {path}"}
        sess = session_from_token(_bearer(headers))
        if os.environ.get("USERDATA_REQUIRE_AUTH") == "1" and not sess:
            return {"ok": False, "error": "Authentication required.", "http_status": 401}
        sub = path[len("/api/userdata"):] or "/"
        if sub in ("/", "/stats") and method == "GET":
            return get_user_data_stats()
        if sub == "/profile":
            return {"ok": True, "profile": get_candidate_profile()} if method == "GET" else update_candidate_profile(payload)
        if sub == "/gmail/sync" and method == "POST":
            return sync_gmail(payload.get("user"), payload.get("password"), payload.get("limit", 50))
        if sub in ("/gmail", "/gmail/messages") and method == "GET":
            owner_filter = str(payload.get("email") or os.environ.get("GMAIL_ADDRESS") or os.environ.get("GMAIL_SMTP_USER") or "").strip().lower()
            with _LOCK, _connect() as con:
                if owner_filter:
                    rows = _rows(con, "SELECT sender, sender_email, subject, snippet, received_at FROM gmail_messages WHERE owner=? ORDER BY received_at DESC LIMIT 100", (owner_filter,))
                    if not rows:
                        rows = _rows(con, "SELECT sender, sender_email, subject, snippet, received_at FROM gmail_messages ORDER BY received_at DESC LIMIT 100")
                else:
                    rows = _rows(con, "SELECT sender, sender_email, subject, snippet, received_at FROM gmail_messages ORDER BY received_at DESC LIMIT 100")
                return {"ok": True, "messages": rows}
        if sub == "/contacts":
            if method == "GET":
                with _LOCK, _connect() as con:
                    return {"ok": True, "contacts": _rows(con, "SELECT * FROM contacts ORDER BY last_seen DESC LIMIT 500")}
            if str(payload.get("action") or "").lower() == "delete":
                return delete_hiring_contact(payload.get("email"))
            return save_hiring_contact(payload)
        if sub == "/applications":
            if method == "GET":
                with _LOCK, _connect() as con:
                    return {"ok": True, "applications": _rows(con, "SELECT * FROM applications ORDER BY created_at DESC")}
            if str(payload.get("action") or "").lower() == "delete":
                return delete_user_application(payload.get("id"))
            return save_user_application(payload)
        if sub == "/export" and method == "GET":
            return {"ok": True, **export_user_data()}
        if sub == "/logout" and method == "POST":
            tok = _bearer(headers) or str(payload.get("session_token") or "")
            with _LOCK, _connect() as con:
                con.execute("UPDATE oauth_sessions SET revoked=1 WHERE token_hash=?", (_hash(tok),))
            return {"ok": True}
        return {"ok": False, "error": f"Unknown endpoint: {method} {path}"}
    except sqlite3.Error as e:
        return {"ok": False, "error": f"Database error ({type(e).__name__})."}


# ---------------------------------------------------------------- standalone server

def serve_user_backend(port=8001, host="127.0.0.1", log=print):
    class H(BaseHTTPRequestHandler):
        def _send(self, res):
            status = res.pop("http_status", None)
            body = json.dumps(res).encode("utf-8")
            self.send_response(status or (200 if res.get("ok") else 400))
            origin = self.headers.get("Origin", "")
            if origin.startswith(("http://127.0.0.1", "http://localhost")):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            origin = self.headers.get("Origin", "")
            if origin.startswith(("http://127.0.0.1", "http://localhost")):
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            self._send(handle_user_data_request(u.path, q, "GET", dict(self.headers)))

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            n = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
            try:
                payload = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            except Exception:
                payload = {}
            self._send(handle_user_data_request(u.path, payload, "POST", dict(self.headers)))

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer((host, int(port)), H)
    log(f"User Data Backend at http://{host}:{port}  (db: {db_path()})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down user backend.")
    finally:
        srv.server_close()
