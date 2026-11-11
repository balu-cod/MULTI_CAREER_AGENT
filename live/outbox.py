"""Human-approved sending of drafts (cold emails, follow-ups). Nothing is sent without a typed 'y' per email."""
import pathlib, shutil
from .profile import ROOT, merged_profile
from .mailer import Mailer, MailError, clean_addr

FOLDERS = ("drafts", "followups")


def parse_draft(path):
    head, _, body = pathlib.Path(path).read_text("utf-8").partition("\n\n")
    hdr = {}
    for line in head.splitlines():
        if ":" in line: k, _, v = line.partition(":"); hdr[k.strip().lower()] = v.strip()
    return hdr, body.strip()


def pending(root=ROOT):
    return [p for f in FOLDERS for p in sorted((pathlib.Path(root) / "private" / f).glob("*.txt"))]


def send_drafts(vault, log=print, ask=input, root=ROOT, dry_run=False):
    mailer = Mailer.from_env(vault, sender_name=merged_profile(vault).get("full_name", ""), dry_run=dry_run)
    if not mailer: log("Set GMAIL_SMTP_USER and GMAIL_SMTP_APP_PASSWORD first."); return {"sent": 0}
    sent = skipped = 0; root = pathlib.Path(root)
    for p in pending(root):
        hdr, body = parse_draft(p)
        try: to = clean_addr(hdr.get("to", ""))
        except MailError: log(f"skip {p.name}: add a valid 'To:' address to the file"); skipped += 1; continue
        log(f"\n--- {p.parent.name}/{p.name}\nTo: {to}\nSubject: {hdr.get('subject', '')}\n{body}\n")
        if ask(f"Send to {to}? [y/N] ").strip().lower() != "y": skipped += 1; continue
        cv = root / "private" / "resumes" / (p.stem + ".pdf")
        try: mailer.send(to, hdr.get("subject", "(no subject)"), body, attachments=[cv] if cv.exists() and p.parent.name == "drafts" else [], kind=p.parent.name)
        except MailError as e: log(f"FAILED {p.name}: {e}"); skipped += 1; continue
        done = root / "private" / "sent"; done.mkdir(parents=True, exist_ok=True); shutil.move(str(p), str(done / p.name)); sent += 1
    log(f"sent {sent}, skipped {skipped}"); return {"sent": sent, "skipped": skipped}


def test_mail(vault, log=print):
    """Send a one-line test to yourself to prove the Gmail credentials work."""
    to = merged_profile(vault).get("contact_email") or __import__("os").getenv("GMAIL_SMTP_USER")
    mailer = Mailer.from_env(vault)
    if not mailer: log("Set GMAIL_SMTP_USER and GMAIL_SMTP_APP_PASSWORD first."); return False
    try: mailer.send(to, "Career Agent test email", "If you can read this, Gmail sending works.", kind="test"); log(f"Test email sent to {to}"); return True
    except MailError as e: log(f"FAILED: {e}"); return False
