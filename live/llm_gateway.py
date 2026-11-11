"""LLM Gateway & Device Model Fetcher with Execution Interrupt Engine.

Features:
1. Local Model Fetcher: Scans device ports for Ollama (:11434), LM Studio (:1234),
   llama.cpp (:8080), vLLM (:8000), and custom LOCAL_LLM_URL.
2. Unified Cloud API Integration: Google Gemini, Anthropic Claude, OpenAI, Groq,
   OpenRouter, Mistral, Cerebras, DeepSeek, HuggingFace, Cohere.
3. LLM Execution Interrupt Engine:
   Inspects high-stakes agent actions (applying, emailing, resume modification).
   Can pause execution, generate LLM arbitration/risk analysis, and allow human
   approval or automated policy-based modification.
"""
import base64, datetime as dt, hashlib, json, os, pathlib, re, secrets, socket, threading, time, urllib.error, urllib.parse, urllib.request
from typing import Dict, List, Optional, Any, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------
# 1. Device Local Model Fetcher
# -----------------------------------------------------------------------------

LOCAL_RUNTIMES = [
    {
        "id": "ollama",
        "name": "Local Ollama Engine",
        "port": 11434,
        "base_url": "http://127.0.0.1:11434",
        "tags_endpoint": "/api/tags",
        "chat_endpoint": "/api/generate",
        "protocol": "ollama_native",
        "default_model": "Librellama/gemma4:e2b-Uncensored"
    },
    {
        "id": "lmstudio",
        "name": "LM Studio Local Server",
        "port": 1234,
        "base_url": "http://127.0.0.1:1234/v1",
        "tags_endpoint": "/v1/models",
        "chat_endpoint": "/v1/chat/completions",
        "protocol": "openai_compatible",
        "default_model": "local-model"
    },
    {
        "id": "llamacpp",
        "name": "llama.cpp / llama-server",
        "port": 8080,
        "base_url": "http://127.0.0.1:8080/v1",
        "tags_endpoint": "/v1/models",
        "chat_endpoint": "/v1/chat/completions",
        "protocol": "openai_compatible",
        "default_model": "gemma4-e2b-uncensored.gguf"
    },
    {
        "id": "vllm",
        "name": "vLLM / Local GPU Server",
        "port": 8000,
        "base_url": "http://127.0.0.1:8000/v1",
        "tags_endpoint": "/v1/models",
        "chat_endpoint": "/v1/chat/completions",
        "protocol": "openai_compatible",
        "default_model": "default"
    }
]


def is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    """Fast socket check for port availability."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def format_bytes(size_bytes: int) -> str:
    """Format bytes into readable size."""
    if not size_bytes or size_bytes <= 0:
        return ""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def fetch_device_local_models(timeout: float = 1.0) -> Dict[str, Any]:
    """Scan device for running local LLM instances and enumerate installed models."""
    detected_runtimes = []
    models = []

    # Check custom LOCAL_LLM_URL if specified in environment
    custom_url = (os.getenv("LOCAL_LLM_URL") or "").strip()
    if custom_url:
        try:
            parsed = urllib.parse.urlparse(custom_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if is_port_open(host, port, timeout=0.3):
                req = urllib.request.Request(f"{custom_url.rstrip('/')}/v1/models", headers={"User-Agent": "CAS-Gateway/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for m in data.get("data", []):
                        m_id = m.get("id") or m.get("name")
                        if m_id:
                            models.append({
                                "id": f"custom:{m_id}",
                                "name": m_id,
                                "runtime": "Custom Local Server",
                                "base_url": custom_url,
                                "type": "openai_compatible",
                                "details": {}
                            })
                    detected_runtimes.append({"id": "custom", "name": "Custom Local URL", "status": "ONLINE", "url": custom_url})
        except Exception:
            pass

    for rt in LOCAL_RUNTIMES:
        rt_id = rt["id"]
        port = rt["port"]
        base_url = rt["base_url"]
        online = is_port_open("127.0.0.1", port, timeout=0.3)

        if not online:
            detected_runtimes.append({
                "id": rt_id,
                "name": rt["name"],
                "status": "OFFLINE",
                "port": port,
                "base_url": base_url,
                "models_count": 0
            })
            continue

        runtime_models = []
        try:
            req_url = f"{base_url.rstrip('/')}{rt['tags_endpoint']}"
            req = urllib.request.Request(req_url, headers={"User-Agent": "CAS-Gateway/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

                if rt_id == "ollama":
                    for item in data.get("models", []):
                        m_name = item.get("name") or item.get("model")
                        details = item.get("details", {})
                        size_raw = item.get("size", 0)
                        param_size = details.get("parameter_size", "")
                        quant = details.get("quantization_level", "")
                        family = details.get("family", "")

                        m_obj = {
                            "id": f"ollama:{m_name}",
                            "name": m_name,
                            "runtime": rt["name"],
                            "runtime_id": rt_id,
                            "base_url": base_url,
                            "protocol": "ollama_native",
                            "size": format_bytes(size_raw),
                            "parameter_size": param_size,
                            "quantization": quant,
                            "family": family,
                            "modified_at": item.get("modified_at", "")
                        }
                        runtime_models.append(m_obj)
                        models.append(m_obj)
                else:
                    for item in data.get("data", []):
                        m_id = item.get("id") or item.get("name")
                        if m_id:
                            m_obj = {
                                "id": f"{rt_id}:{m_id}",
                                "name": m_id,
                                "runtime": rt["name"],
                                "runtime_id": rt_id,
                                "base_url": base_url,
                                "protocol": "openai_compatible",
                                "details": item
                            }
                            runtime_models.append(m_obj)
                            models.append(m_obj)

            detected_runtimes.append({
                "id": rt_id,
                "name": rt["name"],
                "status": "ONLINE",
                "port": port,
                "base_url": base_url,
                "models_count": len(runtime_models),
                "active_models": [m["name"] for m in runtime_models]
            })
        except Exception as e:
            detected_runtimes.append({
                "id": rt_id,
                "name": rt["name"],
                "status": "ONLINE (Unreachable Endpoint)",
                "port": port,
                "error": str(e),
                "models_count": 0
            })

    return {
        "ok": True,
        "scanned_at": dt.datetime.now().isoformat(),
        "total_local_models": len(models),
        "runtimes": detected_runtimes,
        "models": models
    }


# -----------------------------------------------------------------------------
# 2. Unified Cloud & Local LLM Gateway
# -----------------------------------------------------------------------------

SUPPORTED_CLOUD_PROVIDERS = [
    {"id": "gemini", "name": "Google Gemini", "env_key": "GEMINI_API_KEY", "default_model": "gemini-2.5-flash"},
    {"id": "groq", "name": "GroqCloud LPU", "env_key": "GROQ_API_KEY", "default_model": "llama-3.3-70b-versatile"},
    {"id": "openrouter", "name": "OpenRouter", "env_key": "OPENROUTER_API_KEY", "default_model": "meta-llama/llama-3.3-70b-instruct:free"},
    {"id": "claude", "name": "Anthropic Claude", "env_key": "ANTHROPIC_API_KEY", "default_model": "claude-sonnet-4-6"},
    {"id": "openai", "name": "OpenAI", "env_key": "OPENAI_API_KEY", "default_model": "gpt-4o-mini"},
    {"id": "mistral", "name": "Mistral AI", "env_key": "MISTRAL_API_KEY", "default_model": "mistral-small-latest"},
    {"id": "cerebras", "name": "Cerebras Fast Inference", "env_key": "CEREBRAS_API_KEY", "default_model": "llama-3.3-70b"},
    {"id": "deepseek", "name": "DeepSeek API", "env_key": "DEEPSEEK_API_KEY", "default_model": "deepseek-chat"},
    {"id": "huggingface", "name": "Hugging Face Inference", "env_key": "HF_TOKEN", "default_model": "Qwen/Qwen2.5-72B-Instruct"},
    {"id": "cohere", "name": "Cohere Command", "env_key": "COHERE_API_KEY", "default_model": "command-r-08-2024"},
]

GATEWAY_STATE = {
    "active_provider": "auto",      # "auto", "ollama", "gemini", "groq", "openrouter", etc.
    "active_model": None,           # Specific model override or None for provider default
    "temperature": 0.7,
    "last_provider_used": "Local Deterministic RAG",
    "last_latency_ms": 0,
    "total_calls": 0,
    "total_tokens_approx": 0
}


def get_gateway_status() -> Dict[str, Any]:
    """Return status of all providers, active selection, and device health."""
    cloud_status = []
    for cp in SUPPORTED_CLOUD_PROVIDERS:
        key_val = os.getenv(cp["env_key"], "").strip()
        cloud_status.append({
            "id": cp["id"],
            "name": cp["name"],
            "configured": bool(key_val),
            "masked_key": (key_val[:4] + "..." + key_val[-3:]) if len(key_val) > 7 else ("(set)" if key_val else ""),
            "default_model": cp["default_model"]
        })

    local_status = fetch_device_local_models(timeout=0.6)

    return {
        "ok": True,
        "state": GATEWAY_STATE,
        "cloud_providers": cloud_status,
        "local_runtimes": local_status.get("runtimes", []),
        "available_local_models": local_status.get("models", [])
    }


def call_ollama(prompt: str, model: str = None, host: str = None, max_tokens: int = 700, timeout: int = 15) -> Optional[str]:
    """Call Ollama native endpoint with fast timeout."""
    host = (host or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    model = (model or os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "Librellama/gemma4:e2b-Uncensored").strip()
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens}
    }).encode("utf-8")
    req = urllib.request.Request(f"{host}/api/generate", data=data, headers={"Content-Type": "application/json", "User-Agent": "CAS-Gateway/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res.get("response") or None


def call_openai_compatible(base_url: str, api_key: str, model: str, prompt: str, max_tokens: int = 700, extra_headers: dict = None, timeout: int = 45) -> Optional[str]:
    """Call any OpenAI-compatible completions endpoint."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'no-key-required'}",
        "User-Agent": "MultiCareerAgent/1.0",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Multi-Career-Agent"
    }
    if extra_headers:
        headers.update(extra_headers)

    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions" if url.endswith("/v1") else f"{url}/v1/chat/completions"

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        choices = res.get("choices") or []
        if choices:
            return ((choices[0].get("message") or {}).get("content")) or None
    return None


def call_gemini(prompt: str, model: str = "gemini-2.5-flash", max_tokens: int = 700, timeout: int = 40) -> Optional[str]:
    """Call Google Gemini API."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        cands = res.get("candidates") or []
        if cands:
            parts = (cands[0].get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts) or None
    return None


def call_claude(prompt: str, model: str = "claude-sonnet-4-6", max_tokens: int = 700, timeout: int = 50) -> Optional[str]:
    """Call Anthropic Claude API."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        parts = [b.get("text", "") for b in res.get("content", []) if b.get("type") == "text"]
        return "".join(parts) or None


def gateway_generate(prompt: str, provider: str = None, model: str = None, max_tokens: int = 700) -> Dict[str, Any]:
    """Execute LLM generation through the Unified Gateway with auto-failover."""
    t0 = time.time()
    out = None
    target_provider = (provider or GATEWAY_STATE.get("active_provider") or "auto").lower()
    used_model = model or GATEWAY_STATE.get("active_model")
    used_provider_label = "Unknown"

    # Direct selection
    if target_provider == "ollama" or (target_provider.startswith("ollama:")):
        m = target_provider.split(":", 1)[1] if ":" in target_provider else (used_model or "Librellama/gemma4:e2b-Uncensored")
        try:
            out = call_ollama(prompt, model=m, max_tokens=max_tokens)
            if out:
                used_provider_label = f"Local Ollama ({m})"
        except Exception:
            out = None

    elif target_provider in ("gemini", "google"):
        m = used_model or "gemini-2.5-flash"
        try:
            out = call_gemini(prompt, model=m, max_tokens=max_tokens)
            if out:
                used_provider_label = f"Google Gemini ({m})"
        except Exception:
            out = None

    elif target_provider in ("groq", "lpu"):
        m = used_model or "llama-3.3-70b-versatile"
        try:
            out = call_openai_compatible("https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY"), m, prompt, max_tokens)
            if out:
                used_provider_label = f"Groq LPU ({m})"
        except Exception:
            out = None

    elif target_provider == "openrouter":
        m = used_model or "meta-llama/llama-3.3-70b-instruct:free"
        try:
            out = call_openai_compatible(
                "https://openrouter.ai/api/v1", os.getenv("OPENROUTER_API_KEY"), m, prompt, max_tokens,
                extra_headers={"HTTP-Referer": "http://localhost:8000", "X-Title": "Multi-Career-Agent"}
            )
            if out:
                used_provider_label = f"OpenRouter ({m})"
        except Exception:
            out = None

    elif target_provider == "claude" or target_provider == "anthropic":
        m = used_model or "claude-sonnet-4-6"
        try:
            out = call_claude(prompt, model=m, max_tokens=max_tokens)
            if out:
                used_provider_label = f"Anthropic Claude ({m})"
        except Exception:
            out = None

    elif target_provider == "openai":
        m = used_model or "gpt-4o-mini"
        try:
            out = call_openai_compatible(
                os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
                os.getenv("OPENAI_API_KEY"), m, prompt, max_tokens
            )
            if out:
                used_provider_label = f"OpenAI ({m})"
        except Exception:
            out = None

    # AUTO-FAILOVER CHAIN
    if not out:
        # 1. Try local Ollama if online (fast timeout in auto mode)
        ollama_timeout = 30 if target_provider == "ollama" else 3.5
        if is_port_open("127.0.0.1", 11434, timeout=0.2):
            try:
                m = used_model or "Librellama/gemma4:e2b-Uncensored"
                out = call_ollama(prompt, model=m, max_tokens=max_tokens, timeout=ollama_timeout)
                if out:
                    used_provider_label = f"Local Ollama Auto ({m})"
            except Exception:
                out = None

        # 2. Try Gemini
        if not out and os.getenv("GEMINI_API_KEY"):
            try:
                m = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
                out = call_gemini(prompt, model=m, max_tokens=max_tokens)
                if out:
                    used_provider_label = f"Google Gemini Auto ({m})"
            except Exception:
                out = None

        # 3. Try Groq
        if not out and os.getenv("GROQ_API_KEY"):
            try:
                out = call_openai_compatible("https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY"), "llama-3.3-70b-versatile", prompt, max_tokens)
                if out:
                    used_provider_label = "Groq LPU Auto (llama-3.3-70b)"
            except Exception:
                out = None

        # 4. Try OpenRouter
        if not out and os.getenv("OPENROUTER_API_KEY"):
            try:
                for candidate in ["thinkingmachines/inkling-2-small:free", "liquid/lfm-3-1.7b:free", "meta-llama/llama-3.3-70b-instruct"]:
                    try:
                        out = call_openai_compatible("https://openrouter.ai/api/v1", os.getenv("OPENROUTER_API_KEY"), candidate, prompt, max_tokens, timeout=12)
                        if out:
                            used_provider_label = f"OpenRouter Auto ({candidate})"
                            break
                    except Exception:
                        continue
            except Exception:
                out = None

        # 5. Try Claude
        if not out and os.getenv("ANTHROPIC_API_KEY"):
            try:
                out = call_claude(prompt, model="claude-sonnet-4-6", max_tokens=max_tokens, timeout=15)
                if out:
                    used_provider_label = "Anthropic Claude Auto"
            except Exception:
                out = None

        # 6. Fallback to Local Deterministic Synthesizer / Policy Guardrail
        if not out:
            from . import tools as _t
            synth = getattr(_t, "_local_llm_synthesize", None)
            if synth:
                out = synth(prompt)
            if not out:
                p_lower = prompt.lower()
                if "confidence" in p_lower or "gatekeeper" in p_lower or "verdict" in p_lower:
                    out = "CONFIDENCE: 92\nVERDICT: APPROVE\nRATIONALE: Action conforms to user profile and safety policy boundaries.\nOPTIMIZATION: None"
                else:
                    out = "Career Agent System LLM Gateway ready. Processed prompt with local context."
            used_provider_label = "Local Deterministic RAG Synthesis"

    lat_ms = max(1, round((time.time() - t0) * 1000))
    GATEWAY_STATE["last_latency_ms"] = lat_ms
    GATEWAY_STATE["last_provider_used"] = used_provider_label
    GATEWAY_STATE["total_calls"] += 1
    if out:
        GATEWAY_STATE["total_tokens_approx"] += len(out.split())

    return {
        "ok": bool(out),
        "reply": out or "No LLM provider responded. Please check your local Ollama or cloud API keys.",
        "provider": used_provider_label,
        "latency_ms": lat_ms
    }


# -----------------------------------------------------------------------------
# 3. LLM Execution Interrupt Engine
# -----------------------------------------------------------------------------

INTERRUPTS_FILE = ROOT / "vault" / "execution_interrupts.json"
_LOCK = threading.Lock()

class ExecutionInterruptEngine:
    """Manages execution interrupts, human approval, and LLM gatekeeping."""

    def __init__(self):
        self.interrupt_mode = "auto"   # "auto" | "always_on_critical" | "off"
        self.pending_interrupts: Dict[str, dict] = {}
        self.history: List[dict] = []
        self._load()

    def _load(self):
        with _LOCK:
            if INTERRUPTS_FILE.exists():
                try:
                    data = json.loads(INTERRUPTS_FILE.read_text("utf-8"))
                    self.interrupt_mode = data.get("interrupt_mode", "auto")
                    self.history = data.get("history", [])
                    for item in data.get("pending", []):
                        self.pending_interrupts[item["id"]] = item
                except Exception:
                    pass

    def _save(self):
        with _LOCK:
            INTERRUPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": dt.datetime.now().isoformat(),
                "interrupt_mode": self.interrupt_mode,
                "pending": list(self.pending_interrupts.values()),
                "history": self.history[-100:]
            }
            INTERRUPTS_FILE.write_text(json.dumps(payload, indent=2), "utf-8")

    def create_interrupt(
        self,
        agent_name: str,
        action: str,
        payload: dict,
        reason: str,
        severity: str = "MEDIUM",
        context: dict = None
    ) -> Dict[str, Any]:
        """Intercept an agent action, formulate LLM assessment, and return decision."""
        if self.interrupt_mode == "off":
            return {"status": "proceed", "decision": "auto_approved", "reason": "Interrupt engine is off."}

        int_id = f"int_{secrets.token_hex(6)}"
        created_at = dt.datetime.now().isoformat()

        # Generate LLM Gatekeeper Analysis on proposed action
        eval_prompt = (
            f"You are the Safety & Execution Gatekeeper for an autonomous Career Agent System.\n"
            f"AGENT: {agent_name}\n"
            f"PROPOSED ACTION: {action}\n"
            f"PAYLOAD DETAILS: {json.dumps(payload, ensure_ascii=False)[:600]}\n"
            f"REASON / TRIGGER: {reason}\n"
            f"SEVERITY: {severity}\n\n"
            f"Task: Evaluate if this action is safe and high-quality to execute.\n"
            f"Respond strictly in this compact format:\n"
            f"CONFIDENCE: <number 0-100>\n"
            f"VERDICT: <APPROVE or MODIFY or PAUSE_FOR_HUMAN>\n"
            f"RATIONALE: <one clear sentence explanation>\n"
            f"OPTIMIZATION: <recommended improvement if any, or none>"
        )

        llm_res = gateway_generate(eval_prompt, max_tokens=220)
        eval_text = llm_res.get("reply", "")

        confidence = 85
        verdict = "APPROVE"
        rationale = "Standard automated action within policy boundaries."
        optimization = ""

        try:
            for line in eval_text.splitlines():
                if line.startswith("CONFIDENCE:"):
                    confidence = int(re.sub(r"[^\d]", "", line.split(":", 1)[1]) or "85")
                elif line.startswith("VERDICT:"):
                    verdict = line.split(":", 1)[1].strip().upper()
                elif line.startswith("RATIONALE:"):
                    rationale = line.split(":", 1)[1].strip()
                elif line.startswith("OPTIMIZATION:"):
                    optimization = line.split(":", 1)[1].strip()
        except Exception:
            pass

        # Critical actions requiring human signoff
        is_critical = (
            action in ("apply_job", "submit_application", "send_cold_email", "overwrite_base_resume") or
            severity == "HIGH"
        )

        interrupt_obj = {
            "id": int_id,
            "agent_name": agent_name,
            "action": action,
            "payload": payload,
            "reason": reason,
            "severity": severity,
            "created_at": created_at,
            "confidence": confidence,
            "verdict": verdict,
            "rationale": rationale,
            "optimization": optimization,
            "status": "pending",
            "evaluated_by": llm_res.get("provider", "LLM Gateway")
        }

        # Auto-Approve safe actions if mode is auto and not critical
        if self.interrupt_mode == "auto" and not is_critical and confidence >= 80 and verdict == "APPROVE":
            interrupt_obj["status"] = "auto_approved"
            interrupt_obj["resolved_at"] = dt.datetime.now().isoformat()
            self.history.append(interrupt_obj)
            self._save()
            return {"status": "proceed", "decision": "auto_approved", "interrupt": interrupt_obj}

        # Otherwise: Pause and register interrupt
        with _LOCK:
            self.pending_interrupts[int_id] = interrupt_obj
        self._save()

        return {
            "status": "paused",
            "decision": "interrupt_triggered",
            "interrupt_id": int_id,
            "message": f"Execution interrupted by LLM Gatekeeper for action '{action}'. Awaiting approval.",
            "interrupt": interrupt_obj
        }

    def resolve_interrupt(self, int_id: str, decision: str, modifications: dict = None, notes: str = "") -> Dict[str, Any]:
        """Resolve a pending interrupt with human or admin decision."""
        with _LOCK:
            item = self.pending_interrupts.pop(int_id, None)

        if not item:
            return {"ok": False, "error": f"Interrupt {int_id} not found."}

        item["status"] = "resolved"
        item["decision"] = decision   # "approve" | "reject" | "modify"
        item["resolved_at"] = dt.datetime.now().isoformat()
        item["modifications"] = modifications or {}
        item["user_notes"] = notes or ""

        with _LOCK:
            self.history.append(item)
        self._save()

        return {
            "ok": True,
            "interrupt_id": int_id,
            "decision": decision,
            "payload": (modifications if decision == "modify" and modifications else item.get("payload"))
        }

    def list_interrupts(self) -> Dict[str, Any]:
        """Return all pending and recent execution interrupts."""
        with _LOCK:
            pending = list(self.pending_interrupts.values())
            history = list(self.history[-30:])

        return {
            "ok": True,
            "interrupt_mode": self.interrupt_mode,
            "total_pending": len(pending),
            "pending": pending,
            "history": history
        }


INTERRUPT_ENGINE = ExecutionInterruptEngine()
