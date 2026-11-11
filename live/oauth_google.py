"""Google OAuth 2.0 Authorization Code flow with PKCE.

Handles:
  - Generating the authorization URL (with PKCE, state, nonce, offline access + Gmail scopes)
  - Exchanging the code for tokens at Google's token endpoint
  - Verifying the returned ID token locally (iss/aud/exp/nonce/email_verified)
  - Refreshing access tokens
  - Revoking tokens at Google

Environment variables consumed:
    GOOGLE_CLIENT_ID       — OAuth Web application client ID (required)
    GOOGLE_CLIENT_SECRET   — OAuth client secret  (required)
    PUBLIC_BASE_URL        — Canonical origin, e.g. http://localhost:8000 (optional, auto-detected)
    OAUTH_TOKEN_URL        — Override token endpoint (tests only)
    GMAIL_API_BASE         — Override Gmail REST base (tests only)

Security notes:
  - PKCE (S256) is always used so the secret is not needed in the browser.
  - state and nonce are stored in a short-lived HttpOnly cookie (cas_oauth) and
    verified on callback to prevent CSRF and replay.
  - The returned authorization code is single-use: Google rejects replays.
"""
import base64, hashlib, json, os, secrets, time, urllib.error, urllib.parse, urllib.request
from typing import Optional, Tuple, Dict, Any

# ---------------------------------------------------------------- endpoints
GOOGLE_AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_CERTS_URL  = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS    = ("accounts.google.com", "https://accounts.google.com")

# Gmail scopes we request
SCOPE_OPENID   = "openid"
SCOPE_EMAIL    = "https://www.googleapis.com/auth/userinfo.email"
SCOPE_PROFILE  = "https://www.googleapis.com/auth/userinfo.profile"
SCOPE_GMAIL_R  = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_GMAIL_S  = "https://www.googleapis.com/auth/gmail.send"

ALL_SCOPES = [SCOPE_OPENID, SCOPE_EMAIL, SCOPE_PROFILE, SCOPE_GMAIL_R, SCOPE_GMAIL_S]

# ---------------------------------------------------------------- PKCE helpers

def new_pkce() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge_S256)."""
    verifier = secrets.token_urlsafe(64)          # 86+ chars, URL-safe base64
    digest    = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _rnd(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


# ---------------------------------------------------------------- config helpers

def _client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()


def _token_url() -> str:
    return os.environ.get("OAUTH_TOKEN_URL", "") or GOOGLE_TOKEN_URL


def missing_config() -> list:
    """Return names of required env vars that are empty."""
    missing = []
    if not _client_id():
        missing.append("GOOGLE_CLIENT_ID")
    if not _client_secret():
        missing.append("GOOGLE_CLIENT_SECRET")
    return missing


def redirect_uri(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/auth/google/callback"


# ---------------------------------------------------------------- authorization URL

def build_auth_url(base_url: str) -> Dict[str, str]:
    """
    Return {"url": <Google auth URL>, "state": s, "nonce": n, "code_verifier": v}.
    The caller must persist state + nonce + code_verifier in the pending cookie.
    """
    verifier, challenge = new_pkce()
    state = _rnd(24)
    nonce = _rnd(24)
    scopes = " ".join(ALL_SCOPES)
    params = {
        "response_type":         "code",
        "client_id":             _client_id(),
        "redirect_uri":          redirect_uri(base_url),
        "scope":                 scopes,
        "state":                 state,
        "nonce":                 nonce,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "access_type":           "offline",
        "prompt":                "consent",   # always return refresh_token
    }
    url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return {"url": url, "state": state, "nonce": nonce, "code_verifier": verifier}


# ---------------------------------------------------------------- token exchange

def _post_form(url: str, data: dict) -> dict:
    body    = urllib.parse.urlencode(data).encode("ascii")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    req     = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(raw)
        except Exception:
            err = {"error": "http_error", "error_description": raw[:200]}
        raise OAuthError(err.get("error", "http_error"), err.get("error_description", raw[:200]))


class OAuthError(Exception):
    def __init__(self, code: str, description: str = ""):
        self.code        = code
        self.description = description
        super().__init__(f"{code}: {description}")


def exchange_code(code: str, code_verifier: str, base_url: str) -> dict:
    """Exchange auth code + PKCE verifier for tokens. Returns the raw Google token response."""
    missing = missing_config()
    if missing:
        raise OAuthError("not_configured", f"Missing: {', '.join(missing)}")
    return _post_form(_token_url(), {
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  redirect_uri(base_url),
        "client_id":     _client_id(),
        "client_secret": _client_secret(),
        "code_verifier": code_verifier,
    })


def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh_token to get a new access_token. Returns raw token response."""
    return _post_form(_token_url(), {
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     _client_id(),
        "client_secret": _client_secret(),
    })


def revoke_token(token: str) -> bool:
    """Revoke a refresh or access token at Google. Returns True on success."""
    try:
        _post_form(GOOGLE_REVOKE_URL, {"token": token})
        return True
    except OAuthError:
        return False


# ---------------------------------------------------------------- ID token verification (local, no network)

def _b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _decode_jwt_payload(id_token: str) -> dict:
    parts = id_token.split(".")
    if len(parts) != 3:
        raise OAuthError("invalid_token", "ID token is not a JWT")
    return json.loads(_b64url_decode(parts[1]).decode("utf-8"))


def verify_id_token_claims(id_token: str, nonce: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Verify the claims inside an ID token without fetching Google's certs (we already trust the
    token because we just received it from Google's token endpoint over TLS; full signature
    verification would require fetching certs but is optional for server-side code that obtained
    the token directly — this is consistent with Google's own guidance for server flows).

    Returns (claims, None) on success or (None, error_message).
    """
    try:
        claims = _decode_jwt_payload(id_token)
    except Exception as e:
        return None, f"Could not decode ID token: {e}"

    cid = _client_id()
    if cid and claims.get("aud") != cid:
        return None, "Token audience does not match GOOGLE_CLIENT_ID."
    if claims.get("iss") not in GOOGLE_ISSUERS:
        return None, "Token issuer is not Google."
    try:
        if int(claims.get("exp", 0)) < int(time.time()):
            return None, "ID token has expired."
    except (TypeError, ValueError):
        return None, "ID token has no valid expiry."
    if nonce and claims.get("nonce") != nonce:
        return None, "ID token nonce does not match."
    if str(claims.get("email_verified")).lower() != "true":
        return None, "Google account email is not verified."
    if not claims.get("sub"):
        return None, "ID token has no subject (sub)."
    if not claims.get("email"):
        return None, "ID token has no email."
    return claims, None


# ---------------------------------------------------------------- granted-scope helper

def granted_scopes(token_response: dict) -> list:
    """Return list of granted scopes from a token response."""
    s = token_response.get("scope", "")
    return s.split() if s else []
