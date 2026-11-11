"""Centralized .env/ folder & secret key loader for all Career Agent System agents.
Supports:
  1. .env/secrets.env (and any .env/*.env file)
  2. .env/keys.json (structured JSON key-value store)
  3. .env/<KEY_NAME> (individual secret files inside .env/ folder)
  4. Fallback to private/.env or a root .env file if present
Automatically synchronizes aliases (GMAIL_ADDRESS <-> GMAIL_SMTP_USER, GMAIL_APP_PASSWORD <-> GMAIL_SMTP_APP_PASSWORD)
and registers get_secret / env_status in the agent TOOLS registry.
"""
import json, os, pathlib, re, stat

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FOLDER = ROOT / ".env"

AGENT_KEY_SPECS = [
    ("GMAIL_ADDRESS", "", ["inbox", "digest", "outbox", "followup"], "Gmail address for sending digests & reading replies (alias: GMAIL_SMTP_USER)"),
    ("GMAIL_APP_PASSWORD", "", ["inbox", "digest", "outbox", "followup"], "16-char Google App Password (spaces stripped automatically; alias: GMAIL_SMTP_APP_PASSWORD)"),
    ("GMAIL_SMTP_USER", "", ["inbox", "digest", "outbox"], "SMTP/IMAP login username (auto-synced with GMAIL_ADDRESS)"),
    ("GMAIL_SMTP_APP_PASSWORD", "", ["inbox", "digest", "outbox"], "SMTP/IMAP 16-char App Password (auto-synced with GMAIL_APP_PASSWORD)"),
    ("GEMINI_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep", "builder"], "Google Gemini API key for LLM resume summaries & cold emails"),
    ("GEMINI_MODEL", "gemini-2.5-flash", ["tailor", "drafter"], "Gemini model name (default: gemini-2.5-flash)"),
    ("ANTHROPIC_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep", "builder"], "Anthropic Claude API key for LLM synthesis & agent generation"),
    ("CLAUDE_MODEL", "claude-sonnet-4-6", ["tailor", "drafter", "builder"], "Anthropic Claude model name"),
    ("GROQ_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep", "builder"], "100% Free GroqCloud API key (llama-3.3-70b-versatile, no card needed)"),
    ("MISTRAL_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep", "builder"], "100% Free Mistral La Plateforme Experiment API key (mistral-small-latest)"),
    ("HF_TOKEN", "", ["tailor", "drafter", "prep", "interviewprep"], "100% Free Hugging Face Access Token for Serverless Inference API"),
    ("COHERE_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep"], "100% Free Cohere Trial API key (command-r-08-2024)"),
    ("OPENROUTER_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep"], "100% Free OpenRouter API key (uses :free models by default)"),
    ("OPENAI_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep"], "OpenAI API key (optional paid provider)"),
    ("OLLAMA_HOST", "http://localhost:11434", ["tailor", "drafter"], "Local Ollama server URL (optional)"),
    ("OLLAMA_MODEL", "", ["tailor", "drafter"], "Local Ollama model tag (e.g., qwen2.5-coder:7b)"),
    ("LOCAL_LLM_URL", "", ["tailor", "drafter", "prep", "interviewprep"], "Local or tunnel OpenAI-compatible server URL (llama-server :8080, LM Studio :1234, vLLM :8000, trycloudflare.com)"),
    ("CEREBRAS_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep"], "Cerebras Wafer-Scale Inference API key (csk-...)"),
    ("XAI_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep"], "xAI Grok API key (xai-...)"),
    ("PERPLEXITY_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep"], "Perplexity Sonar API key (pplx-...)"),
    ("DEEPSEEK_API_KEY", "", ["tailor", "drafter", "prep", "interviewprep"], "DeepSeek API key"),
    ("YOUTUBE_API_KEY", "", ["youtube"], "Optional YouTube Data API v3 key (Atom feeds work without a key)"),
    ("GITHUB_TOKEN", "", ["aiupdates", "scanner"], "Optional GitHub Personal Access Token for higher API rate limits"),
    ("GOOGLE_CLIENT_ID", "", ["userdata", "inbox", "digest", "outbox"], "Google OAuth 2.0 Web client ID (Google Cloud Console > Credentials)"),
    ("GOOGLE_CLIENT_SECRET", "", ["userdata", "inbox", "digest", "outbox"], "Google OAuth 2.0 Web client secret (GOCSPX-...) for PKCE + Gmail REST API"),
    ("PUBLIC_BASE_URL", "", ["userdata"], "Optional canonical base URL for OAuth 2.0 callback (default: http://localhost:8000)"),
    ("USERDATA_REQUIRE_AUTH", "0", ["userdata"], "1 = every /api/userdata call needs a Bearer session token"),
    ("USERDATA_DEV_AUTH", "0", ["userdata"], "1 = allow unverified local sign-in when GOOGLE_CLIENT_ID is unset (development only)"),
    ("APPLY_MODE", "off", ["autoapply"], "Auto-apply mode: off | dry-run | submit"),
]

ALIASES = [
    ("GMAIL_ADDRESS", "GMAIL_SMTP_USER"),
    ("GMAIL_APP_PASSWORD", "GMAIL_SMTP_APP_PASSWORD"),
]

KNOWN_KEYS = {k for k, _, _, _ in AGENT_KEY_SPECS} | {"LLM_MODEL", "LLM_BASE_URL", "APPLY_CONFIRM", "PROFILE_JSON", "RESUME_B64", "HEADED", "AUTH_ALLOWED_EMAILS", "AUTH_ALLOWED_DOMAINS", "SESSION_IDLE_HOURS", "SESSION_MAX_DAYS"}
_KV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _parse_env_text(text):
    """Parse KEY=VALUE lines, stripping quotes and inline # comments."""
    out = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _KV_LINE.match(line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        else:
            v = re.sub(r"\s+#.*$", "", v).strip()
        out[k] = v
    return out


def _chmod_private(path):
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def ensure_env_folder(root=ROOT):
    """Create the .env/ folder with secrets.env, keys.json, secrets.env.example, and README.md if missing."""
    env_dir = pathlib.Path(root) / ".env"
    if env_dir.is_file():
        existing = _parse_env_text(env_dir.read_text("utf-8", errors="ignore"))
        env_dir.unlink()
        env_dir.mkdir(parents=True, exist_ok=True)
    else:
        env_dir.mkdir(parents=True, exist_ok=True)
        existing = {}

    secrets_env = env_dir / "secrets.env"
    keys_json = env_dir / "keys.json"
    example_env = env_dir / "secrets.env.example"
    readme_md = env_dir / "README.md"

    template_lines = [
        "# ============================================================================",
        "# CAREER AGENT SYSTEM v6.5 — .env/secrets.env (Agent Secret Keys Vault)",
        "# ============================================================================",
        "# All 18 agents automatically load non-empty keys from this .env/ folder.",
        "# Protected by .gitignore: secrets.env and keys.json are NEVER committed.",
        "",
        "# --- 1. Gmail SMTP & IMAP Credentials (inbox, digest, outbox, followup) ---",
        f"GMAIL_ADDRESS={existing.get('GMAIL_ADDRESS', '')}",
        f"GMAIL_APP_PASSWORD={existing.get('GMAIL_APP_PASSWORD', '')}",
        f"GMAIL_SMTP_USER={existing.get('GMAIL_SMTP_USER', '')}",
        f"GMAIL_SMTP_APP_PASSWORD={existing.get('GMAIL_SMTP_APP_PASSWORD', '')}",
        "",
        "# --- 2. LLM API Keys (tailor, drafter, prep, interviewprep, builder) ---",
        f"GEMINI_API_KEY={existing.get('GEMINI_API_KEY', '')}",
        f"GEMINI_MODEL={existing.get('GEMINI_MODEL', 'gemini-2.5-flash')}",
        f"ANTHROPIC_API_KEY={existing.get('ANTHROPIC_API_KEY', '')}",
        f"CLAUDE_MODEL={existing.get('CLAUDE_MODEL', 'claude-sonnet-4-6')}",
        f"GROQ_API_KEY={existing.get('GROQ_API_KEY', '')}",
        f"MISTRAL_API_KEY={existing.get('MISTRAL_API_KEY', '')}",
        f"HF_TOKEN={existing.get('HF_TOKEN', '')}",
        f"COHERE_API_KEY={existing.get('COHERE_API_KEY', '')}",
        f"OPENROUTER_API_KEY={existing.get('OPENROUTER_API_KEY', '')}",
        f"OPENAI_API_KEY={existing.get('OPENAI_API_KEY', '')}",
        f"OLLAMA_HOST={existing.get('OLLAMA_HOST', 'http://localhost:11434')}",
        f"OLLAMA_MODEL={existing.get('OLLAMA_MODEL', '')}",
        "",
        "# --- 3. Discovery & Automation Keys (youtube, aiupdates, autoapply) ---",
        f"YOUTUBE_API_KEY={existing.get('YOUTUBE_API_KEY', '')}",
        f"GITHUB_TOKEN={existing.get('GITHUB_TOKEN', '')}",
        f"APPLY_MODE={existing.get('APPLY_MODE', 'off')}",
        "",
    ]

    if not example_env.exists():
        example_lines = [
            ln if not ln.startswith(("GMAIL_APP_PASSWORD=", "GMAIL_SMTP_APP_PASSWORD=", "GEMINI_API_KEY=", "ANTHROPIC_API_KEY=", "GROQ_API_KEY=", "OPENAI_API_KEY=", "OPENROUTER_API_KEY=", "YOUTUBE_API_KEY=", "GITHUB_TOKEN="))
            else ln.split("=", 1)[0] + "="
            for ln in template_lines
        ]
        example_env.write_text("\n".join(example_lines), "utf-8")

    if not secrets_env.exists():
        secrets_env.write_text("\n".join(template_lines), "utf-8")
        _chmod_private(secrets_env)

    if not keys_json.exists():
        default_json = {k: existing.get(k, default) for k, default, _, _ in AGENT_KEY_SPECS}
        keys_json.write_text(json.dumps(default_json, indent=2) + "\n", "utf-8")
        _chmod_private(keys_json)

    if not readme_md.exists():
        readme_md.write_text(
            "# `.env/` Agent Secret Keys Folder\n\n"
            "All 18 agents in `career_agent_system.py` automatically load secrets from this folder on startup via `live/env_loader.py`.\n\n"
            "## 3 Ways to Store Keys Here\n"
            "1. **Edit `.env/secrets.env`**: Standard `KEY=VALUE` lines.\n"
            "2. **Edit `.env/keys.json`**: Structured JSON object.\n"
            "3. **CLI Command**: Run `python3 career_agent_system.py --set-key KEY=VALUE` or drop a single-key file `.env/<KEY_NAME>`.\n\n"
            "## Check Loaded Keys\n"
            "```bash\n"
            "python3 career_agent_system.py --mode check-env\n"
            "```\n",
            "utf-8",
        )
    return env_dir


def read_env_folder_values(root=ROOT):
    """Read all key-value pairs stored in the .env/ folder without mutating os.environ."""
    root = pathlib.Path(root)
    env_dir = root / ".env"
    merged = {}

    if env_dir.is_file():
        merged.update(_parse_env_text(env_dir.read_text("utf-8", errors="ignore")))
    elif env_dir.is_dir():
        # 1. Read keys.json first
        kj = env_dir / "keys.json"
        if kj.is_file():
            try:
                data = json.loads(kj.read_text("utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if v is not None and str(v).strip() != "":
                            merged[str(k).strip()] = str(v).strip()
            except Exception:
                pass
        # 2. Read secrets.env and any other *.env files (excluding *.example)
        env_files = sorted(p for p in env_dir.glob("*.env") if not p.name.endswith(".example"))
        for ef in env_files:
            try:
                for k, v in _parse_env_text(ef.read_text("utf-8", errors="ignore")).items():
                    if v != "":
                        merged[k] = v
            except Exception:
                pass
        # 3. Read individual uppercase key files (.env/GEMINI_API_KEY, .env/GMAIL_APP_PASSWORD, etc.)
        for child in sorted(env_dir.iterdir()):
            if child.is_file() and child.name.isupper() and "_" in child.name and "." not in child.name:
                try:
                    val = child.read_text("utf-8", errors="ignore").strip()
                    if val:
                        merged[child.name] = val
                except Exception:
                    pass

    # 4. Also check private/.env if present
    priv_env = root / "private" / ".env"
    if priv_env.is_file():
        for k, v in _parse_env_text(priv_env.read_text("utf-8", errors="ignore")).items():
            if v != "" and k not in merged:
                merged[k] = v

    # Normalize Gmail app password spaces and sync aliases
    for pw_key in ("GMAIL_APP_PASSWORD", "GMAIL_SMTP_APP_PASSWORD"):
        if merged.get(pw_key):
            merged[pw_key] = merged[pw_key].replace(" ", "")
    for a, b in ALIASES:
        if merged.get(a) and not merged.get(b):
            merged[b] = merged[a]
        elif merged.get(b) and not merged.get(a):
            merged[a] = merged[b]

    return merged


def load_env(root=ROOT, override=False):
    """Load non-empty secret keys from .env/ folder into os.environ and return loaded dict."""
    ensure_env_folder(root)
    vals = read_env_folder_values(root)
    loaded = {}
    for k, v in vals.items():
        if not v:
            continue
        if override or not os.environ.get(k):
            os.environ[k] = v
            loaded[k] = v
    # Also sync aliases if already present in os.environ
    for a, b in ALIASES:
        va, vb = os.environ.get(a, ""), os.environ.get(b, "")
        if va and not vb:
            os.environ[b] = va.replace(" ", "") if "PASSWORD" in b else va
        elif vb and not va:
            os.environ[a] = vb.replace(" ", "") if "PASSWORD" in a else vb
    return loaded


def set_secret(key, value, root=ROOT):
    """Persist a secret key into both .env/secrets.env and .env/keys.json with 0600 permissions."""
    key = key.strip()
    value = str(value).strip()
    if "PASSWORD" in key and "GMAIL" in key:
        value = value.replace(" ", "")
    env_dir = ensure_env_folder(root)

    # Update keys.json
    kj = env_dir / "keys.json"
    try:
        data = json.loads(kj.read_text("utf-8")) if kj.is_file() else {}
    except Exception:
        data = {}
    data[key] = value
    for a, b in ALIASES:
        if key == a:
            data[b] = value
        elif key == b:
            data[a] = value
    kj.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    _chmod_private(kj)

    # Update secrets.env
    se = env_dir / "secrets.env"
    lines = se.read_text("utf-8").splitlines() if se.is_file() else []
    keys_to_write = {key: value}
    for a, b in ALIASES:
        if key == a:
            keys_to_write[b] = value
        elif key == b:
            keys_to_write[a] = value

    found = set()
    new_lines = []
    for ln in lines:
        m = _KV_LINE.match(ln.strip()) if not ln.strip().startswith("#") else None
        if m and m.group(1) in keys_to_write:
            k = m.group(1)
            new_lines.append(f"{k}={keys_to_write[k]}")
            found.add(k)
        else:
            new_lines.append(ln)
    for k, v in keys_to_write.items():
        if k not in found:
            new_lines.append(f"{k}={v}")
    se.write_text("\n".join(new_lines) + "\n", "utf-8")
    _chmod_private(se)

    for k, v in keys_to_write.items():
        if v:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    return keys_to_write


def mask_value(key, val):
    if not val:
        return "(empty)"
    if any(w in key.upper() for w in ("PASSWORD", "KEY", "TOKEN", "SECRET")):
        if len(val) <= 6:
            return "***"
        return val[:3] + "..." + val[-3:] + f" ({len(val)} chars)"
    return val


def get_secret(key, default="", root=ROOT):
    """Agent helper tool: get a secret from os.environ or .env/ folder."""
    val = os.environ.get(key)
    if val:
        return val
    vals = read_env_folder_values(root)
    return vals.get(key, default)


def env_status(root=ROOT):
    """Return structured status of the .env/ folder and all agent secret keys (values masked)."""
    env_dir = ensure_env_folder(root)
    folder_vals = read_env_folder_values(root)
    rows = []
    for key, default, agents, desc in AGENT_KEY_SPECS:
        raw = os.environ.get(key) or folder_vals.get(key, "")
        is_secret = any(w in key for w in ("PASSWORD", "KEY", "TOKEN"))
        status = "READY" if (raw and (not is_secret or len(raw) >= 4)) else "NOT_SET"
        source = "os.environ" if os.environ.get(key) and key not in folder_vals else (".env/ folder" if raw else "none")
        rows.append({
            "key": key,
            "status": status,
            "masked": mask_value(key, raw),
            "source": source,
            "agents": agents,
            "description": desc,
        })
    return {
        "env_folder": str(env_dir),
        "files": [p.name for p in sorted(env_dir.iterdir()) if p.is_file()],
        "keys": rows,
    }


# Regex patterns to detect raw API key tokens or KEY=VALUE lines inside Gmail messages
TOKEN_PATTERNS = {
    "GEMINI_API_KEY": re.compile(r"\b(AIza[0-9A-Za-z_\-]{35})\b"),
    "GITHUB_TOKEN": re.compile(r"\b((?:ghp|github_pat)_[0-9A-Za-z_]{30,255})\b"),
    "GROQ_API_KEY": re.compile(r"\b(gsk_[0-9A-Za-z]{40,80})\b"),
    "HF_TOKEN": re.compile(r"\b(hf_[0-9A-Za-z]{30,80})\b"),
    "OPENROUTER_API_KEY": re.compile(r"\b(sk-or-v1-[0-9a-f]{64})\b"),
    "ANTHROPIC_API_KEY": re.compile(r"\b(sk-ant-[0-9A-Za-z_\-]{40,120})\b"),
    "OPENAI_API_KEY": re.compile(r"\b(sk-(?:proj-|svcacct-)?[0-9A-Za-z_\-]{32,160})\b"),
    "CEREBRAS_API_KEY": re.compile(r"\b(csk-[0-9A-Za-z_\-]{24,120})\b"),
    "XAI_API_KEY": re.compile(r"\b(xai-[0-9A-Za-z_\-]{24,120})\b"),
    "PERPLEXITY_API_KEY": re.compile(r"\b(pplx-[0-9A-Za-z_\-]{24,120})\b"),
    "GOOGLE_CLIENT_SECRET": re.compile(r"\b(GOCSPX-[0-9A-Za-z_\-]{20,80})\b"),
}


def extract_keys_from_text(text):
    """Extract both explicit KEY=VALUE pairs and recognizable token prefixes (AIza..., ghp_..., gsk_..., hf_...) from email text."""
    found = {}
    for k, v in _parse_env_text(text or "").items():
        if k in KNOWN_KEYS and v:
            found[k] = v
    for key_name, rx in TOKEN_PATTERNS.items():
        if key_name not in found:
            m = rx.search(text or "")
            if m:
                found[key_name] = m.group(1)
    return found


def fetch_keys_from_gmail(root=ROOT, log=print):
    """Connect to Gmail via IMAP (read-only) using GMAIL_ADDRESS + GMAIL_APP_PASSWORD, scan recent messages
    for API keys/tokens (YouTube, Gemini, GitHub, Groq, Hugging Face, OpenRouter, Mistral, etc.), and save them into .env/."""
    import imaplib, email
    from .agents import _hdr, _body
    load_env(root)
    user = os.getenv("GMAIL_SMTP_USER") or os.getenv("GMAIL_ADDRESS")
    pw = (os.getenv("GMAIL_SMTP_APP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    if not (user and pw):
        log("! Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env/secrets.env first to fetch keys from Gmail.")
        return {}
    discovered = {}
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(user, pw)
        m.select("INBOX", readonly=True)
        typ, data = m.search(None, "ALL")
        ids = (data[0] or b"").split()[-80:]
        for msg_id in ids:
            raw = m.fetch(msg_id, "(BODY.PEEK[])")[1][0][1]
            msg = email.message_from_bytes(raw)
            subj = _hdr(msg.get("Subject", ""))
            body = _body(msg)
            extracted = extract_keys_from_text(f"{subj}\n{body}")
            if extracted:
                # If an AIza... key is in an email mentioning YouTube, also map to YOUTUBE_API_KEY
                if "GEMINI_API_KEY" in extracted and "youtube" in (subj + " " + body).lower() and "YOUTUBE_API_KEY" not in extracted:
                    extracted["YOUTUBE_API_KEY"] = extracted["GEMINI_API_KEY"]
                discovered.update(extracted)
        m.logout()
    except Exception as e:
        log(f"! Gmail IMAP key scan error: {e}")
        return {}

    for k, v in discovered.items():
        set_secret(k, v, root=root)
    if discovered:
        log(f"Fetched & saved {len(discovered)} key(s) from Gmail into .env/: {sorted(discovered.keys())}")
    else:
        log("Scanned Gmail inbox — no plaintext API key tokens (AIza..., ghp_..., gsk_..., hf_...) found in email bodies.")
    return discovered
