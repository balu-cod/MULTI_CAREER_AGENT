"""Autonomous Timing-Based Gmail Scheduler Daemon.
Manages scheduled dispatches of Daily Tech News (06:00 IST), Morning Job Digest (08:00 IST),
and Evening Review & Study Plan (20:00 IST) with email safeguards and audit ledger logging.
"""
import datetime as dt, os, threading, time
from .profile import ROOT, merged_profile
from . import runtime
from . import user_data_backend as udb

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
_SCHEDULER_THREAD = None
_RUNNING = False
_FIRED_KEYS = set()
_LAST_RUNS = {}

DAILY_NEWS_AGENTS = ["scanner", "aiupdates", "youtube", "contests", "matcher", "dailynews"]


def get_schedule_settings():
    """Returns configured dispatch timings (in IST)."""
    return {
        "daily_news": os.getenv("SCHEDULE_DAILY_NEWS", "06:00"),
        "morning_digest": os.getenv("SCHEDULE_MORNING_DIGEST", "08:00"),
        "evening_review": os.getenv("SCHEDULE_EVENING_REVIEW", "20:00"),
        "auto_send": os.getenv("AUTO_SEND_SCHEDULED", "1") == "1",
        "timezone": "Asia/Kolkata (IST, UTC+5:30)"
    }


def trigger_scheduled_now(mode, vault, log=print):
    """Trigger an immediate scheduled dispatch for testing or on-demand execution."""
    from .env_loader import load_env
    load_env(ROOT)
    runtime.discover()
    
    p = merged_profile(vault)
    cand_email = p.get("contact_email") or os.getenv("GMAIL_SMTP_USER") or os.getenv("GMAIL_ADDRESS")
    
    log(f"[Scheduler] Executing '{mode}' dispatch for {cand_email}...")
    
    if mode == "daily-news":
        os.environ["DAILY_NEWS_SEND"] = "1"
        os.environ["DIGEST_SEND"] = "0"
        ctx = runtime.run_pipeline(vault, log, only_agents=DAILY_NEWS_AGENTS)
    elif mode == "evening-review":
        os.environ["EVENING_REVIEW_SEND"] = "1"
        os.environ["DIGEST_SEND"] = "0"
        ctx = runtime.run_pipeline(vault, log)
    else:  # morning-digest
        os.environ["DIGEST_SEND"] = "1"
        os.environ["DAILY_NEWS_SEND"] = "0"
        os.environ["EVENING_REVIEW_SEND"] = "0"
        ctx = runtime.run_pipeline(vault, log)
        
    _LAST_RUNS[mode] = dt.datetime.now(IST).isoformat()
    
    udb.record_ledger_action(
        "GMAIL_SENT",
        f"SCHEDULED_{mode.upper().replace('-', '_')}",
        f"Executed {mode} dispatch. Target: {cand_email}.",
        actor="GMAIL_SCHEDULER"
    )
    
    return {
        "ok": True,
        "mode": mode,
        "timestamp": _LAST_RUNS[mode],
        "jobs_count": len(ctx.get("jobs", [])),
        "matches_count": len(ctx.get("matches", []))
    }


def _scheduler_loop(vault, log):
    global _RUNNING
    log("[Scheduler Daemon] Started autonomous timing loop (06:00 Daily News | 08:00 Morning Digest | 20:00 Evening Review IST).")
    while _RUNNING:
        try:
            cfg = get_schedule_settings()
            if cfg["auto_send"]:
                now = dt.datetime.now(IST)
                time_str = now.strftime("%H:%M")
                date_str = now.date().isoformat()
                
                checks = [
                    (cfg["daily_news"], "daily-news"),
                    (cfg["morning_digest"], "morning-digest"),
                    (cfg["evening_review"], "evening-review")
                ]
                
                for target_time, mode in checks:
                    key = (date_str, target_time, mode)
                    if time_str == target_time and key not in _FIRED_KEYS:
                        _FIRED_KEYS.add(key)
                        log(f"[Scheduler Daemon] Clock matched {target_time} IST. Launching {mode}...")
                        trigger_scheduled_now(mode, vault, log=log)
        except Exception as e:
            log(f"[Scheduler Daemon] Loop error: {e}")
        time.sleep(25)


def start_background_scheduler(vault, log=print):
    """Starts the 24/7 background scheduler thread."""
    global _SCHEDULER_THREAD, _RUNNING
    if _RUNNING and _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return False
    _RUNNING = True
    _SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, args=(vault, log), daemon=True)
    _SCHEDULER_THREAD.start()
    return True


def get_scheduler_status():
    """Returns current scheduler status and telemetry."""
    cfg = get_schedule_settings()
    now_ist = dt.datetime.now(IST)
    return {
        "ok": True,
        "running": _RUNNING,
        "current_time_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
        "schedule": cfg,
        "last_runs": _LAST_RUNS
    }
