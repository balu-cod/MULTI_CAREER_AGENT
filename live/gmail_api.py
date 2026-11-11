"""Gmail REST API client (uses OAuth 2.0 access tokens, not App Passwords).

Public helpers used by agents, mailer and server:
    connected_account(mode)       → email str or None
    list_messages(email, limit)   → list[dict]
    sync_messages(email, limit)   → {"ok", "new_messages", "total_stored", "transport"}
    send_message(email, to, subject, body, attachments, sender_name) → {"status", "via"}

Environment:
    GMAIL_API_BASE  — override for tests (default https://www.googleapis.com/gmail/v1)
"""
import base64, email as email_lib, email.mime.application, email.mime.multipart
import email.mime.text, json, os, pathlib, time, urllib.error, urllib.parse, urllib.request
from typing import Optional

GMAIL_BASE = "https://www.googleapis.com/gmail/v1"

# scopes we need
SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"


# ---------------------------------------------------------------- low-level HTTP

def _api_base() -> str:
    return (os.environ.get("GMAIL_API_BASE") or GMAIL_BASE).rstrip("/")


def _get(path: str, access_token: str, params: dict = None) -> dict:
    url = _api_base() + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"error": {"code": e.code, "message": raw[:200]}}
        raise GmailError(e.code, body)


def _post(path: str, access_token: str, body_bytes: bytes, content_type: str = "application/json") -> dict:
    url = _api_base() + path
    req = urllib.request.Request(
        url, data=body_bytes,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"error": {"code": e.code, "message": raw[:200]}}
        raise GmailError(e.code, body)


class GmailError(Exception):
    def __init__(self, status: int, body: dict):
        self.status = status
        self.body   = body
        err         = body.get("error", {}) if isinstance(body, dict) else {}
        self.code   = err.get("code", status)
        self.message = err.get("message", str(body))
        # detect specific sub-errors
        errors       = err.get("errors", [{}])
        self.reason  = errors[0].get("reason", "") if errors else ""
        super().__init__(f"Gmail API {status}: {self.message}")


# ---------------------------------------------------------------- token refresh integration

def _get_with_refresh(path: str, email: str, params: dict = None) -> dict:
    """Call Gmail API, transparently refreshing a stale access token once."""
    from . import accounts
    for attempt in range(2):
        tok = accounts.fresh_access_token(email)
        if tok is None:
            raise GmailError(401, {"error": {"code": 401, "message": "No valid token; re-auth required."}})
        try:
            return _get(path, tok, params)
        except GmailError as e:
            if e.status == 401 and attempt == 0:
                # force a refresh and retry once
                accounts.invalidate_access_token(email)
                continue
            raise


def _post_with_refresh(path: str, email: str, body_bytes: bytes, content_type: str = "application/json") -> dict:
    from . import accounts
    for attempt in range(2):
        tok = accounts.fresh_access_token(email)
        if tok is None:
            raise GmailError(401, {"error": {"code": 401, "message": "No valid token; re-auth required."}})
        try:
            return _post(path, tok, body_bytes, content_type)
        except GmailError as e:
            if e.status == 401 and attempt == 0:
                accounts.invalidate_access_token(email)
                continue
            raise


# ---------------------------------------------------------------- scope checks

def connected_account(mode: str = "read") -> Optional[str]:
    """Return the email of the connected account that has the given mode ('read' or 'send'), or None."""
    from . import accounts
    email = accounts.owner_email()
    if not email:
        return None
    tokens = accounts.get_tokens(email)
    if not tokens:
        return None
    scopes = tokens.get("scopes", [])
    needed = SCOPE_READ if mode == "read" else SCOPE_SEND
    return email if needed in scopes else None


# ---------------------------------------------------------------- message listing

def _decode_header(raw: str) -> str:
    try:
        import email.header as eh
        parts = eh.decode_header(raw or "")
        return str(eh.make_header(parts))
    except Exception:
        return raw or ""


def _header(headers: list, name: str) -> str:
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def list_messages(email: str, limit: int = 50) -> list:
    """
    Fetch up to `limit` message headers from Gmail API.
    Returns list of dicts: {message_id, sender, sender_email, subject, snippet, received_at}.
    """
    # list message IDs
    listing = _get_with_refresh(f"/users/{email}/messages", email, {"maxResults": min(limit, 100), "labelIds": "INBOX"})
    msgs_meta = listing.get("messages", [])
    results = []
    for m in msgs_meta[:limit]:
        try:
            msg = _get_with_refresh(f"/users/{email}/messages/{m['id']}", email, {"format": "metadata", "metadataHeaders": "From,Subject,Date"})
            hdrs        = msg.get("payload", {}).get("headers", [])
            from_raw    = _header(hdrs, "From")
            # parse "Name <email@example.com>"
            if "<" in from_raw:
                name_part  = from_raw[:from_raw.index("<")].strip().strip('"')
                email_part = from_raw[from_raw.index("<")+1:].rstrip(">").strip()
            else:
                name_part  = ""
                email_part = from_raw.strip()
            # received_at from internalDate (ms epoch)
            ts = int(msg.get("internalDate", 0)) / 1000
            received_at = None
            if ts:
                import datetime as dt
                received_at = dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            results.append({
                "message_id":   m["id"],
                "sender":       _decode_header(name_part) or email_part,
                "sender_email": email_part.lower(),
                "subject":      _decode_header(_header(hdrs, "Subject")),
                "snippet":      msg.get("snippet", ""),
                "received_at":  received_at,
            })
        except GmailError:
            continue
    return results


# ---------------------------------------------------------------- Gmail sync to SQLite

def sync_messages(email: str, limit: int = 50) -> dict:
    """
    Pull messages from Gmail API and store headers in sqlite (gmail_messages table).
    Returns {"ok", "transport", "new_messages", "total_stored"}.
    """
    from . import user_data_backend as udb
    from . import accounts

    # check scopes
    tokens = accounts.get_tokens(email)
    if not tokens or SCOPE_READ not in tokens.get("scopes", []):
        return {"ok": False, "error": "Gmail read permission not granted. Please sign in again and grant Gmail access."}

    try:
        messages = _list_with_retry(email, limit)
    except GmailError as e:
        if e.status == 401:
            # revoked grant
            accounts.mark_needs_reauth(email)
            return {"ok": False, "error": "Gmail access was revoked. Please sign in again."}
        if e.status == 403:
            body_err = e.body.get("error", {}) if isinstance(e.body, dict) else {}
            errors   = body_err.get("errors", [{}])
            reason   = errors[0].get("reason", "") if errors else ""
            if reason == "accessNotConfigured":
                return {"ok": False, "error": "Enable the Gmail API in your Google Cloud project (APIs & Services → Library → Gmail API → Enable)."}
            return {"ok": False, "error": f"Gmail API access denied: {e.message}"}
        if e.status == 429:
            return {"ok": False, "error": f"Gmail API rate limited: {e.message}"}
        return {"ok": False, "error": str(e)}

    new_count = 0
    with udb._LOCK, udb._connect() as con:
        for m in messages:
            try:
                con.execute(
                    "INSERT OR IGNORE INTO gmail_messages (owner,message_id,sender,sender_email,subject,snippet,received_at,folder,synced_at) VALUES (?,?,?,?,?,?,?,'INBOX',?)",
                    (email.lower(), m["message_id"], m["sender"], m["sender_email"], m["subject"], m["snippet"], m["received_at"], udb._iso()),
                )
                if con.execute("SELECT changes()").fetchone()[0]:
                    new_count += 1
            except Exception:
                continue
        total = con.execute("SELECT COUNT(*) FROM gmail_messages WHERE owner=?", (email.lower(),)).fetchone()[0]

    return {"ok": True, "transport": "gmail_api", "new_messages": new_count, "total_stored": total}


def _list_with_retry(email: str, limit: int, max_retries: int = 3) -> list:
    """List messages with exponential back-off on 429."""
    for attempt in range(max_retries):
        try:
            return list_messages(email, limit)
        except GmailError as e:
            if e.status == 429 and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise


# ---------------------------------------------------------------- sending

def send_message(
    email: str,
    to: str,
    subject: str,
    body: str,
    attachments: list = None,
    sender_name: str = "",
) -> dict:
    """Send an email via Gmail API. Returns {"status": "sent", "via": "gmail_api"}."""
    from . import accounts
    tokens = accounts.get_tokens(email)
    if not tokens or SCOPE_SEND not in tokens.get("scopes", []):
        raise GmailError(403, {"error": {"code": 403, "message": "Gmail send permission not granted."}})

    # build MIME message
    if attachments:
        msg = email_lib.mime.multipart.MIMEMultipart()
        msg.attach(email_lib.mime.text.MIMEText(body, "plain", "utf-8"))
        for path in (attachments or []):
            p = pathlib.Path(path)
            with open(p, "rb") as f:
                part = email_lib.mime.application.MIMEApplication(f.read(), Name=p.name)
            part["Content-Disposition"] = f'attachment; filename="{p.name}"'
            msg.attach(part)
    else:
        msg = email_lib.mime.text.MIMEText(body, "plain", "utf-8")

    from_addr = f"{sender_name} <{email}>" if sender_name else email
    msg["From"]    = from_addr
    msg["To"]      = to
    msg["Subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    _post_with_refresh(
        f"/users/{email}/messages/send", email,
        json.dumps({"raw": raw}).encode("utf-8"),
    )
    return {"status": "sent", "via": "gmail_api"}
