"""Tool registry + dependency-ordered orchestrator for the live agents (plugs into the existing VaultAgent)."""
import importlib, json, pathlib
from .profile import ROOT, merged_profile, PRIVATE_KEYS

TOOLS, AGENTS = {}, {}


def tool(fn):
    TOOLS[fn.__name__] = fn
    return fn


def agent(cls):
    AGENTS[cls.name] = cls
    return cls


class LiveAgent:
    name, needs, soft_needs, doc = "base", [], [], ""

    def run(self, ctx):
        raise NotImplementedError


def discover():
    importlib.import_module("live.tools")
    importlib.import_module("live.agents")
    for f in sorted((ROOT / "live" / "custom").glob("[!_]*.py")):
        importlib.import_module(f"live.custom.{f.stem}")


def run_pipeline(vault, log, only_agents=None, extra_ctx=None):
    import datetime as dt
    discover()
    try:
        from . import tools as _t
        _t._PAGES.clear()
    except Exception:
        pass
    cfg = json.loads((ROOT / "live" / "pipeline.json").read_text())
    public = vault.load_artifact("user_profile_v1.json", agent_name="LIVE_PIPELINE_AGENT") or {}
    lines, failed, started = [], set(), dt.datetime.now(dt.timezone.utc)

    def L(m):
        lines.append(str(m))
        log(m)

    leaked = [k for k in PRIVATE_KEYS if k in public]
    if leaked:
        L(f"! private fields {leaked} found in the committed Vault profile; move them to private/profile.json")
    ctx = {
        "vault": vault,
        "profile": merged_profile(vault),
        "log": L,
        "insights": {},
        "run_log": lines,
        "failed": failed,
        "started": started,
        "run_id": started.strftime("%Y%m%dT%H%M%SZ"),
        **(extra_ctx or {}),
    }
    pending = list(only_agents) if only_agents else list(cfg["agents"])
    order = lambda n: [d for d in (list(getattr(AGENTS.get(n), "needs", [])) + list(getattr(AGENTS.get(n), "soft_needs", []))) if d in pending or d in failed]
    while pending:
        ready = [n for n in pending if not any(d in pending for d in order(n))]
        if not ready:
            L(f"dependency cycle: {pending}")
            break
        for n in ready:
            pending.remove(n)
            cls = AGENTS.get(n)
            if not cls:
                L(f"unknown agent '{n}'")
                failed.add(n)
                continue
            if any(d in failed for d in cls.needs):
                L(f"- {n} skipped (dependency failed)")
                failed.add(n)
                continue
            try:
                L(f"> {n}")
                cls().run(ctx)
            except Exception as e:
                L(f"x {n} failed: {e}")
                failed.add(n)
    return ctx
