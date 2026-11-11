"""Gmail sending over SMTP (app password). Validates addresses, blocks header injection, retries transient errors,
caps daily volume, and writes every send to the audit log."""
import datetime as dt, html, mimetypes, os, pathlib, re, smtplib, time
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr

EMAIL_RE = re.compile(r"^[^@\s<>\",;]+@[^@\s<>\",;]+\.[A-Za-z]{2,}$")


class MailError(RuntimeError):
    pass


def clean_addr(value):
    addr = parseaddr(value or "")[1]
    if not EMAIL_RE.match(addr): raise MailError(f"invalid email address: {value!r}")
    return addr


def _header(value):
    if re.search(r"[\r\n]", value or ""): raise MailError("newline in header value (possible injection)")
    return value


class Mailer:
    def __init__(self, user, password, vault, host="smtp.gmail.com", port=465, daily_cap=40, sender_name="", dry_run=False):
        self.user, self.vault, self.host, self.port = clean_addr(user), vault, host, port
        self.password = (password or "").replace(" ", "")        # Google shows app passwords as 'abcd efgh ijkl mnop'
        self.daily_cap, self.sender_name, self.dry_run = daily_cap, sender_name, dry_run

    @classmethod
    def from_env(cls, vault, **kw):
        user = os.getenv("GMAIL_SMTP_USER") or os.getenv("GMAIL_ADDRESS"); pw = os.getenv("GMAIL_SMTP_APP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
        if user and pw:
            return cls(user, pw, vault, **kw)
        try:
            from . import gmail_api
            oauth_user = gmail_api.connected_account("send")
            if oauth_user:
                return cls(oauth_user, "__OAUTH2__", vault, **kw)
        except Exception:
            pass
        return None

    def sent_today(self):
        p, today, n = pathlib.Path(self.vault.audit_path), dt.datetime.now(dt.timezone.utc).date().isoformat(), 0
        if p.exists():
            for line in p.read_text("utf-8").splitlines():
                if f'"at": "{today}' in line and '"action": "email_sent"' in line: n += 1
        return n

    def build_mime(self, to, subject, text, html_body=None, attachments=(), reply_to=None):
        """Constructs a standards-compliant email.mime MIMEMultipart message with MIMEText and MIMEApplication attachments."""
        root_msg = MIMEMultipart("mixed")
        root_msg["Subject"], root_msg["To"] = _header(subject), clean_addr(to)
        root_msg["From"] = formataddr((_header(self.sender_name), self.user)) if self.sender_name else self.user
        root_msg["Date"], root_msg["Message-ID"] = formatdate(localtime=True), make_msgid(domain=self.user.split("@")[1])
        if reply_to:
            root_msg["Reply-To"] = clean_addr(reply_to)
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text or "", "plain", "utf-8"))
        if html_body:
            alt.attach(MIMEText(html_body, "html", "utf-8"))
        root_msg.attach(alt)
        for path in attachments:
            path = pathlib.Path(path)
            if not path.is_file():
                raise MailError(f"attachment missing: {path}")
            part = MIMEApplication(path.read_bytes(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            root_msg.attach(part)
        return root_msg

    def build(self, to, subject, text, html_body=None, attachments=(), reply_to=None):
        m = EmailMessage()
        m["Subject"], m["To"] = _header(subject), clean_addr(to)
        m["From"] = formataddr((_header(self.sender_name), self.user)) if self.sender_name else self.user
        m["Date"], m["Message-ID"] = formatdate(localtime=True), make_msgid(domain=self.user.split("@")[1])
        if reply_to: m["Reply-To"] = clean_addr(reply_to)
        m.set_content(text)
        if html_body: m.add_alternative(html_body, subtype="html")
        for path in attachments:
            path = pathlib.Path(path)
            if not path.is_file(): raise MailError(f"attachment missing: {path}")
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            m.add_attachment(path.read_bytes(), maintype=ctype.split("/")[0], subtype=ctype.split("/")[1], filename=path.name)
        return m

    def send(self, to, subject, text, html_body=None, attachments=(), kind="mail", tries=3):
        msg = self.build(to, subject, text, html_body, attachments)
        if self.sent_today() >= self.daily_cap: raise MailError(f"daily send cap reached ({self.daily_cap})")
        if self.dry_run:
            self.vault.audit("email_dry_run", kind=kind, to=msg["To"], subject=subject); return {"status": "dry-run", "to": msg["To"]}
        if self.password == "__OAUTH2__":
            try:
                from . import gmail_api
                gmail_api.send_message(self.user, msg["To"], subject, text, attachments=list(attachments), sender_name=self.sender_name)
                self.vault.audit("email_sent", kind=kind, to=msg["To"], subject=subject, attachments=[pathlib.Path(a).name for a in attachments], message_id=msg["Message-ID"], via="gmail_api")
                return {"status": "sent", "to": msg["To"], "message_id": msg["Message-ID"], "via": "gmail_api"}
            except Exception as e:
                raise MailError(f"Gmail OAuth 2.0 API send failed: {e}") from e
        last = None
        for n in range(tries):
            try:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as s:
                    s.login(self.user, self.password); s.send_message(msg)
                self.vault.audit("email_sent", kind=kind, to=msg["To"], subject=subject, attachments=[pathlib.Path(a).name for a in attachments], message_id=msg["Message-ID"])
                return {"status": "sent", "to": msg["To"], "message_id": msg["Message-ID"]}
            except smtplib.SMTPAuthenticationError as e:
                raise MailError("Gmail rejected the login. Use a 16-character App Password (needs 2-Step Verification), not your normal password.") from e
            except smtplib.SMTPRecipientsRefused as e:
                raise MailError(f"recipient refused: {to}") from e
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, TimeoutError, OSError) as e:
                last = e; time.sleep(2 ** n)
        raise MailError(f"send failed after {tries} tries: {last}")


def render_digest(r, I):
    """-> (plain_text, html). Structured multi-section table layout for Gmail; every interpolated value is HTML-escaped."""
    e = lambda x: html.escape(str(x if x is not None else ""))
    link = lambda u, label, style="color:#1E4E79;font-weight:600;text-decoration:none;": (
        f'<a href="{e(u)}" style="{style}">{e(label)}</a>' if str(u).startswith(("https://", "http://")) else e(label)
    )
    t = I.get("today", {})
    f = I.get("funnel", {})
    jobs = r.get("jobs", [])[:12]
    certs = I.get("certs", [])[:10]
    contests = I.get("contests", [])[:8]
    gaps = I.get("skill_gaps", [])
    wproj = I.get("weekend_projects", [])
    ai_up = I.get("ai_updates", [])
    yt = I.get("youtube") or {}
    date_s = str(r.get("updated", ""))[:10]
    head = f"Career Agent digest {date_s}: {r.get('scanned', 0)} scanned, {len(r.get('jobs', []))} matched"

    # ---------------- 1. STRUCTURED PLAIN-TEXT DIGEST ----------------
    sep = "=" * 78
    subsep = "-" * 78
    txt = [
        sep,
        f"CAREER AGENT SYSTEM v6.5 — DAILY STRUCTURED DIGEST ({date_s})",
        head,
        sep,
        "",
        "[1] TODAY'S 4-HOUR EXECUTION SCHEDULE",
        subsep,
    ]
    slot_labels = {
        "morning_7am": "07:00 AM (Morning Study)",
        "evening_630pm": "06:30 PM (Evening DSA)  ",
        "night_9pm": "09:00 PM (Night Build)  ",
        "apply_block": "Daily Apply Block       ",
    }
    for k, v in t.items():
        if k != "date":
            txt.append(f"  * {slot_labels.get(k, k):<26} : {v}")

    txt += ["", "[2] TOP MATCHED JOBS & ATS SCORECARD", subsep]
    for idx, j in enumerate(jobs, 1):
        pay_s = f" | {j['pay']}" if j.get("pay") else ""
        loc_s = j.get("location") or "Remote"
        sk_s = ", ".join((j.get("skills") or [])[:6]) or "general"
        ms_s = ", ".join((j.get("missing") or [])[:4]) or "none"
        txt.append(f"  {idx:>2}. [{j['score']:>2}% Match | ATS {(j.get('ats') if j.get('ats') is not None else '-')}%] {j['title']} @ {j['company']} ({loc_s}{pay_s})")
        txt.append(f"      Matched Skills : {sk_s} | To Learn: {ms_s}")
        txt.append(f"      Apply URL      : {j['url']}")

    txt += [
        "",
        "[3] IN-DEMAND SKILL GAPS & WEEKEND PORTFOLIO PROJECTS",
        subsep,
        "  SKILL GAPS: " + (", ".join(f"{g['skill']} ({g.get('jobs', '')}/{g.get('of', '')})" if g.get("jobs") else g["skill"] for g in gaps) or "none"),
        "  WEEKEND: " + ("; ".join(f"{w['project']} [{w.get('skill', '')}]" for w in wproj) or "none"),
    ]

    if certs:
        txt += ["", "[4] RANKED FREE CERTIFICATIONS & COURSES", subsep]
        for idx, c in enumerate(certs, 1):
            txt.append(f"  {idx:>2}. {c['name']} ({c.get('provider', '')})")
            txt.append(f"      Covers Skills : {', '.join(c.get('covers', []))} | Cost: {c.get('free_claim', 'Free')}")
            txt.append(f"      Course URL    : {c['url']}")

    txt += [
        "",
        "[5] APPLICATION FUNNEL & TRACKER",
        subsep,
        f"  FUNNEL: {f.get('applied', 0)} applied, {f.get('replied', 0)} replied ({f.get('reply_rate', 0)}%), {f.get('interview', 0)} interviews",
    ]
    if I.get("autoapply"):
        txt.append("  AUTO-APPLY: " + str(I["autoapply"]))
    if I.get("followups_due"):
        txt.append("  FOLLOW UP: " + ", ".join(f"{d['title']} @ {d['company']}" for d in I["followups_due"]))

    if ai_up:
        txt += ["", "[6] AI TODAY — REPOS & INDUSTRY SIGNALS", subsep]
        for u in ai_up:
            txt.append(f"  * {u['title']} ({u['source']}) -> {u['url']}")

    for sec, label in (("news", "NEWS VIDEOS"), ("tech", "TECH VIDEOS")):
        if yt.get(sec):
            txt += ["", f"[7] {label}", subsep]
            for v in yt[sec]:
                txt.append(f"  * {v['title']} ({v['channel']}) -> {v['url']}")

    bad = [h for h in I.get("source_health", []) if h.get("error") or not h.get("count")] + [
        {"source": "youtube:" + x["source"], "error": x["error"]} for x in yt.get("health", []) if x.get("error")
    ]
    if bad:
        txt += ["", "SOURCE PROBLEMS: " + ", ".join(f"{h['source']} ({h['error'] or 'zero postings'})" for h in bad)]

    # ---------------- 2. STRUCTURED RICH HTML DIGEST ----------------
    th_style = "padding:10px 12px;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#2E4352;background:#E6EFF6;border-bottom:2px solid #CBD5E1;"
    td_style = "padding:10px 12px;font-size:13px;color:#1E293B;border-bottom:1px solid #E2E8F0;vertical-align:top;"
    sec_title = "margin:24px 0 10px 0;padding-bottom:6px;border-bottom:2px solid #2E4352;color:#2E4352;font-size:16px;font-weight:700;"

    h = [
        '<html><body style="margin:0;padding:20px;background-color:#F5F2EB;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1E293B;">',
        '<div style="max-width:860px;margin:0 auto;background-color:#FCFBF9;border:1px solid #DDD6C7;border-radius:10px;overflow:hidden;">',
        # Top Header Banner
        '<div style="background-color:#2E4352;color:#FFFFFF;padding:20px 24px;">',
        '<div style="font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:#CBD5E1;margin-bottom:4px;">CAREER AGENT SYSTEM v6.5 • AUTONOMOUS 18-AGENT PIPELINE</div>',
        f'<h2 style="margin:0;font-size:20px;font-weight:700;color:#FFFFFF;">{e(head)}</h2>',
        '</div>',
        '<div style="padding:20px 24px;">',
        # KPI Summary Strip Table
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:18px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;"><tr>',
        f'<td style="padding:12px 16px;border-right:1px solid #E2E8F0;width:25%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Scanned Jobs</div><div style="font-size:20px;font-weight:700;color:#2E4352;">{e(r.get("scanned", 0))}</div></td>',
        f'<td style="padding:12px 16px;border-right:1px solid #E2E8F0;width:25%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Matched (&gt;=60%)</div><div style="font-size:20px;font-weight:700;color:#1E6F50;">{e(len(r.get("jobs", [])))}</div></td>',
        f'<td style="padding:12px 16px;border-right:1px solid #E2E8F0;width:25%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Free Certifications</div><div style="font-size:20px;font-weight:700;color:#1E4E79;">{e(len(certs))}</div></td>',
        f'<td style="padding:12px 16px;width:25%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Funnel (Applied / Replied)</div><div style="font-size:16px;font-weight:700;color:#2E4352;">{e(f.get("applied", 0))} / {e(f.get("replied", 0))} ({e(f.get("reply_rate", 0))}%)</div></td>',
        '</tr></table>',
    ]

    # Section 1: Today's Schedule Table
    if any(k != "date" for k in t):
        h.append(f'<h3 style="{sec_title}">1. Today&#39;s 4-Hour Execution Plan ({e(t.get("date", date_s))})</h3>')
        h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
        h.append(f'<thead><tr><th style="{th_style}width:32%;">Time Block</th><th style="{th_style}">Action Item</th></tr></thead><tbody>')
        for k, v in t.items():
            if k != "date":
                h.append(f'<tr><td style="{td_style}font-weight:600;color:#2E4352;">{e(slot_labels.get(k, k).strip())}</td><td style="{td_style}">{e(v)}</td></tr>')
        h.append('</tbody></table>')

    # Section 2: Top Matched Jobs Table
    h.append(f'<h3 style="{sec_title}">2. Top Matched Jobs &amp; ATS Scorecard</h3>')
    if jobs:
        h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
        h.append(
            f'<thead><tr>'
            f'<th style="{th_style}width:6%;">#</th>'
            f'<th style="{th_style}width:14%;">Match / ATS</th>'
            f'<th style="{th_style}width:28%;">Role &amp; Company</th>'
            f'<th style="{th_style}width:18%;">Location &amp; Pay</th>'
            f'<th style="{th_style}width:22%;">Skills &amp; Gaps</th>'
            f'<th style="{th_style}width:12%;">Action</th>'
            f'</tr></thead><tbody>'
        )
        for idx, j in enumerate(jobs, 1):
            pay_html = f'<div style="color:#1E6F50;font-weight:600;font-size:12px;margin-top:2px;">{e(j["pay"])}</div>' if j.get("pay") else ""
            sk_html = e(", ".join((j.get("skills") or [])[:6]) or "Python")
            ms_html = e(", ".join((j.get("missing") or [])[:4]) or "None")
            apply_btn = link(
                j.get("url", ""),
                "Apply ->",
                "display:inline-block;padding:5px 10px;background:#2E4352;color:#FFFFFF;border-radius:5px;font-size:12px;font-weight:600;text-decoration:none;",
            )
            h.append(
                f'<tr>'
                f'<td style="{td_style}font-weight:600;color:#64748B;">{idx}</td>'
                f'<td style="{td_style}"><span style="display:inline-block;padding:3px 7px;background:#E3EFE8;color:#1E6F50;border-radius:4px;font-weight:700;font-size:12px;">{e(j["score"])}% Match</span>'
                f'<div style="font-size:11px;color:#475569;margin-top:4px;">ATS: <b>{e((j.get("ats") if j.get("ats") is not None else "-"))}%</b></div></td>'
                f'<td style="{td_style}">{link(j.get("url", ""), j.get("title", ""))}<div style="font-size:12px;color:#475569;margin-top:2px;"><b>{e(j.get("company", ""))}</b> ({e(j.get("portal", "web"))})</div></td>'
                f'<td style="{td_style}font-size:12px;">{e(j.get("location") or "Remote")}{pay_html}</td>'
                f'<td style="{td_style}font-size:12px;"><div><b style="color:#1E6F50;">Matched:</b> {sk_html}</div><div style="margin-top:3px;color:#B45309;"><b>Learn:</b> {ms_html}</div></td>'
                f'<td style="{td_style}">{apply_btn}</td>'
                f'</tr>'
            )
        h.append('</tbody></table>')
    else:
        h.append('<p style="font-size:13px;color:#64748B;">No matched postings in this run.</p>')

    # Section 3: Skill Gaps & Weekend Portfolio Projects
    h.append(f'<h3 style="{sec_title}">3. In-Demand Skill Gaps &amp; Weekend Portfolio Ideas</h3>')
    gap_pills = ", ".join(
        f"{e(g['skill'])} ({e(g['jobs'])}/{e(g['of'])} jobs)" if g.get("jobs") else e(g["skill"])
        for g in gaps
    )
    h.append(f'<p style="margin:6px 0 10px 0;font-size:13px;"><b>Skill gaps across scanned postings:</b> {gap_pills or "None"}</p>')
    if wproj:
        h.append('<ul style="margin:0 0 12px 18px;padding:0;font-size:13px;">')
        for w in wproj:
            h.append(f'<li style="margin-bottom:4px;"><b>{e(w.get("skill", "").upper())}:</b> {e(w.get("project", ""))}</li>')
        h.append('</ul>')

    # Section 4: Free Certifications Table
    if certs:
        h.append(f'<h3 style="{sec_title}">4. Ranked Free Certifications &amp; Courses (Matched to Your Gaps)</h3>')
        h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
        h.append(
            f'<thead><tr>'
            f'<th style="{th_style}width:6%;">#</th>'
            f'<th style="{th_style}width:38%;">Course / Certification</th>'
            f'<th style="{th_style}width:20%;">Provider</th>'
            f'<th style="{th_style}width:20%;">Skills Covered</th>'
            f'<th style="{th_style}width:16%;">Access</th>'
            f'</tr></thead><tbody>'
        )
        for idx, c in enumerate(certs, 1):
            h.append(
                f'<tr>'
                f'<td style="{td_style}color:#64748B;font-weight:600;">{idx}</td>'
                f'<td style="{td_style}">{link(c.get("url", ""), c.get("name", ""))}</td>'
                f'<td style="{td_style}font-size:12px;">{e(c.get("provider", ""))}</td>'
                f'<td style="{td_style}font-size:12px;"><span style="background:#E6EFF6;color:#1E4E79;padding:2px 6px;border-radius:4px;font-weight:600;">{e(", ".join(c.get("covers", [])))}</span></td>'
                f'<td style="{td_style}font-size:11px;color:#1E6F50;">{e(c.get("free_claim", "Free"))}</td>'
                f'</tr>'
            )
        h.append('</tbody></table>')

    # Section 5: AI Today & YouTube Videos
    if ai_up:
        h.append(f'<h3 style="{sec_title}">5. AI Today — Newest Agent, MCP &amp; LLM Signals</h3>')
        h.append('<ul style="margin:0 0 12px 18px;padding:0;font-size:13px;">')
        for u in ai_up:
            h.append(f'<li style="margin-bottom:5px;">{link(u.get("url", ""), u.get("title", ""))} <span style="color:#64748B;font-size:12px;">({e(u.get("source", ""))})</span></li>')
        h.append('</ul>')

    for sec, label in (("news", "News videos"), ("tech", "Tech videos")):
        if yt.get(sec):
            h.append(f'<h3 style="{sec_title}">{e(label)}</h3><ul style="margin:0 0 12px 18px;padding:0;font-size:13px;">')
            for v in yt[sec]:
                h.append(f'<li style="margin-bottom:5px;">{link(v.get("url", ""), v.get("title", ""))} <span style="color:#64748B;font-size:12px;">({e(v.get("channel", ""))})</span></li>')
            h.append('</ul>')

    if I.get("followups_due"):
        h.append('<p style="font-size:13px;"><b>Follow up due:</b> ' + e(", ".join(f"{d['title']} @ {d['company']}" for d in I["followups_due"])) + '</p>')

    h.append(
        f'<p style="font-size:12px;color:#64748B;margin-top:16px;"><b>Funnel:</b> {e(f.get("applied", 0))} applied, '
        f'{e(f.get("replied", 0))} replied ({e(f.get("reply_rate", 0))}%), {e(f.get("interview", 0))} interviews</p>'
    )
    if bad:
        h.append("<p style='color:#b00;font-size:12px;'><b>Source problems:</b> " + e(", ".join(f"{x['source']} ({x['error'] or 'zero postings'})" for x in bad)) + "</p>")

    if contests:
        h.append(f'<h3 style="{sec_title}">4. Active India Hackathons &amp; Engineering Hiring Challenges</h3>')
        h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
        h.append(f'<thead><tr><th style="{th_style}width:44%;">Challenge &amp; Organizer</th><th style="{th_style}width:24%;">Type</th><th style="{th_style}width:32%;">Reward / Offer</th></tr></thead><tbody>')
        for c in contests:
            h.append(
                f'<tr><td style="{td_style}">{link(c.get("url", ""), c.get("title", ""))}<div style="font-size:12px;color:#475569;margin-top:2px;">{e(c.get("organizer", ""))}</div></td>'
                f'<td style="{td_style}font-size:12px;"><span style="background:#E6EFF6;color:#1E4E79;padding:2px 6px;border-radius:4px;font-weight:600;">{e(c.get("type", ""))}</span></td>'
                f'<td style="{td_style}font-size:12px;font-weight:600;color:#1E6F50;">{e(c.get("reward", ""))}</td></tr>'
            )
        h.append('</tbody></table>')

    h.append('</div></div></body></html>')
    return "\n".join(txt), "\n".join(h)


def render_news_email(ai_items, yt_data, india_jobs, date_s="", contests=None):
    """Build structured plain-text and HTML 6:00 AM Daily AI, Tech & India Hiring News Briefing."""
    e = lambda x: html.escape(str(x if x is not None else ""))
    link = lambda u, label, style="color:#1E4E79;font-weight:600;text-decoration:none;": (
        f'<a href="{e(u)}" style="{style}">{e(label)}</a>' if str(u).startswith(("https://", "http://")) else e(label)
    )
    date_s = date_s or dt.date.today().isoformat()
    news_vids = (yt_data or {}).get("news", [])
    tech_vids = (yt_data or {}).get("tech", [])
    ai_items = (ai_items or [])[:10]
    india_jobs = (india_jobs or [])[:10]
    head = f"6:00 AM Daily AI, Tech & India Hiring News — {date_s}"

    sep = "=" * 78
    subsep = "-" * 78
    txt = [
        sep,
        f"CAREER AGENT SYSTEM v6.5 — 6:00 AM MORNING NEWS BRIEFING ({date_s})",
        head,
        sep,
        "",
        "[1] TOP AI, LLM & AGENTIC ENGINEERING NEWS (HACKER NEWS, HUGGING FACE & GITHUB)",
        subsep,
    ]
    for idx, it in enumerate(ai_items, 1):
        txt.append(f"  {idx:>2}. {it.get('title', '')} [{it.get('source', 'Web')}]")
        txt.append(f"      Link: {it.get('url', '')}")

    txt += ["", "[2] NEWEST AI & TECH VIDEOS (YOUTUBE CHANNELS)", subsep]
    for v in news_vids + tech_vids:
        txt.append(f"  * {v.get('title', '')} ({v.get('channel', '')}) -> {v.get('url', '')}")

    txt += ["", "[3] INDIA PRODUCT-COMPANY & STARTUP HIRING PULSE (BENGALURU / HYDERABAD / REMOTE)", subsep]
    for idx, j in enumerate(india_jobs, 1):
        pay_s = f" | {j['pay']}" if j.get("pay") else ""
        txt.append(f"  {idx:>2}. {j.get('title', '')} @ {j.get('company', '')} ({j.get('location', 'India')}{pay_s})")
        txt.append(f"      Apply: {j.get('url', '')}")

    contests = (contests or [])[:8]
    if contests:
        txt += ["", "[4] ACTIVE HACKATHONS & HIRING CHALLENGES (UNSTOP, HACKEREARTH & HACKERRANK)", subsep]
        for idx, c in enumerate(contests, 1):
            txt.append(f"  {idx:>2}. [{c.get('type', 'Hackathon')}] {c.get('title', '')} — {c.get('reward', '')}")
            txt.append(f"      Register: {c.get('url', '')}")

    th_style = "padding:10px 12px;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#2E4352;background:#E6EFF6;border-bottom:2px solid #CBD5E1;"
    td_style = "padding:10px 12px;font-size:13px;color:#1E293B;border-bottom:1px solid #E2E8F0;vertical-align:top;"
    sec_title = "margin:22px 0 10px 0;padding-bottom:6px;border-bottom:2px solid #2E4352;color:#2E4352;font-size:16px;font-weight:700;"

    h = [
        '<html><body style="margin:0;padding:20px;background-color:#F5F2EB;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1E293B;">',
        '<div style="max-width:860px;margin:0 auto;background-color:#FCFBF9;border:1px solid #DDD6C7;border-radius:10px;overflow:hidden;">',
        '<div style="background-color:#2E4352;color:#FFFFFF;padding:20px 24px;">',
        '<div style="font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:#CBD5E1;margin-bottom:4px;">CAREER AGENT SYSTEM v6.5 • 6:00 AM IST DAILY NEWS AGENT</div>',
        f'<h2 style="margin:0;font-size:20px;font-weight:700;color:#FFFFFF;">{e(head)}</h2>',
        '</div>',
        '<div style="padding:20px 24px;">',
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:18px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;"><tr>',
        f'<td style="padding:12px 16px;border-right:1px solid #E2E8F0;width:33%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">AI &amp; GitHub Signals</div><div style="font-size:20px;font-weight:700;color:#2E4352;">{len(ai_items)}</div></td>',
        f'<td style="padding:12px 16px;border-right:1px solid #E2E8F0;width:33%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Tech &amp; AI Videos</div><div style="font-size:20px;font-weight:700;color:#1E4E79;">{len(news_vids) + len(tech_vids)}</div></td>',
        f'<td style="padding:12px 16px;width:34%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">India Product Openings</div><div style="font-size:20px;font-weight:700;color:#1E6F50;">{len(india_jobs)}</div></td>',
        '</tr></table>',
        f'<h3 style="{sec_title}">1. Top AI, LLM &amp; Agentic Engineering News</h3>',
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">',
        f'<thead><tr><th style="{th_style}width:7%;">#</th><th style="{th_style}width:68%;">Headline &amp; Summary</th><th style="{th_style}width:25%;">Source</th></tr></thead><tbody>',
    ]
    for idx, it in enumerate(ai_items, 1):
        h.append(
            f'<tr><td style="{td_style}color:#64748B;font-weight:600;">{idx}</td>'
            f'<td style="{td_style}">{link(it.get("url", ""), it.get("title", ""))}</td>'
            f'<td style="{td_style}font-size:12px;"><span style="background:#E6EFF6;color:#1E4E79;padding:2px 7px;border-radius:4px;font-weight:600;">{e(it.get("source", "Web"))}</span></td></tr>'
        )
    h.append('</tbody></table>')

    if news_vids or tech_vids:
        h.append(f'<h3 style="{sec_title}">2. Newest AI &amp; Software Engineering Videos</h3>')
        h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
        h.append(f'<thead><tr><th style="{th_style}width:68%;">Video Title</th><th style="{th_style}width:32%;">Channel</th></tr></thead><tbody>')
        for v in news_vids + tech_vids:
            h.append(
                f'<tr><td style="{td_style}">{link(v.get("url", ""), v.get("title", ""))}</td>'
                f'<td style="{td_style}font-size:12px;font-weight:600;color:#475569;">{e(v.get("channel", ""))}</td></tr>'
            )
        h.append('</tbody></table>')

    if india_jobs:
        h.append(f'<h3 style="{sec_title}">3. India Product-Company &amp; Startup Hiring Pulse (Razorpay, Postman, Zoho, Enterpret, Karya)</h3>')
        h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
        h.append(f'<thead><tr><th style="{th_style}width:42%;">Role &amp; Company</th><th style="{th_style}width:28%;">Location &amp; Stipend</th><th style="{th_style}width:30%;">Skills</th></tr></thead><tbody>')
        for j in india_jobs:
            pay_s = f" • {j['pay']}" if j.get("pay") else ""
            h.append(
                f'<tr><td style="{td_style}">{link(j.get("url", ""), j.get("title", ""))}<div style="font-size:12px;color:#475569;margin-top:2px;"><b>{e(j.get("company", ""))}</b></div></td>'
                f'<td style="{td_style}font-size:12px;">{e(j.get("location", "India"))}{e(pay_s)}</td>'
                f'<td style="{td_style}font-size:12px;color:#1E6F50;">{e(", ".join((j.get("skills") or [])[:6]) or "Python, SQL, REST")}</td></tr>'
            )
        h.append('</tbody></table>')

    if contests:
        h.append(f'<h3 style="{sec_title}">4. Active India Hackathons &amp; Engineering Hiring Challenges</h3>')
        h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
        h.append(f'<thead><tr><th style="{th_style}width:44%;">Challenge &amp; Organizer</th><th style="{th_style}width:24%;">Type</th><th style="{th_style}width:32%;">Reward / Offer</th></tr></thead><tbody>')
        for c in contests:
            h.append(
                f'<tr><td style="{td_style}">{link(c.get("url", ""), c.get("title", ""))}<div style="font-size:12px;color:#475569;margin-top:2px;">{e(c.get("organizer", ""))}</div></td>'
                f'<td style="{td_style}font-size:12px;"><span style="background:#E6EFF6;color:#1E4E79;padding:2px 6px;border-radius:4px;font-weight:600;">{e(c.get("type", ""))}</span></td>'
                f'<td style="{td_style}font-size:12px;font-weight:600;color:#1E6F50;">{e(c.get("reward", ""))}</td></tr>'
            )
        h.append('</tbody></table>')

    h.append('</div></div></body></html>')
    return "\n".join(txt), "\n".join(h)


def render_evening_review(payload):
    """Build structured plain-text and HTML 7:00 PM Evening Career & Study Wrap-Up Report."""
    e = lambda x: html.escape(str(x if x is not None else ""))
    link = lambda u, label, style="color:#1E4E79;font-weight:600;text-decoration:none;": (
        f'<a href="{e(u)}" style="{style}">{e(label)}</a>' if str(u).startswith(("https://", "http://")) else e(label)
    )
    date_s = payload.get("date") or dt.date.today().isoformat()
    apps = payload.get("applications") or {}
    study = payload.get("tonight_study") or {}
    tm_queue = payload.get("tomorrow_queue") or []
    contests = payload.get("top_contests") or []
    head = f"7:00 PM Evening Career & Study Wrap-Up — {date_s}"

    sep = "=" * 78
    subsep = "-" * 78
    txt = [
        sep,
        f"CAREER AGENT SYSTEM v6.5 — 7:00 PM EVENING REVIEW AGENT ({date_s})",
        head,
        sep,
        "",
        "[1] GMAIL INBOX, BOUNCE ALERTS & COLD OUTREACH DRAFTS AUDIT",
        subsep,
        f"  * Tracked Applications : {payload.get('applications_tracked', 0)} ({payload.get('bounced_count', 0)} bounced -> use direct portal)",
        f"  * Ready Cold Drafts    : {payload.get('drafts_ready', 0)} in private/drafts/",
        f"  * Tailored PDF Resumes : {payload.get('resumes_ready', 0)} in private/resumes/",
    ]
    for jid, a in apps.items():
        txt.append(f"  - [{a.get('status', 'new')}] {a.get('title', '')} @ {a.get('company', '')} -> {a.get('url', '')}")
        if a.get("note"):
            txt.append(f"    Note: {a['note']}")

    txt += [
        "",
        "[2] TONIGHT'S 6:30 PM DSA & 9:00 PM CERTIFICATION STUDY PLAN",
        subsep,
        f"  * 06:30 PM DSA Block         : {study.get('dsa_630pm', '')}",
        f"  * 09:00 PM Certification     : {study.get('cert_900pm', '')}",
        f"  * Hands-On Coding Task       : {study.get('hands_on_task', '')}",
        f"  * Active Flashcard Topics    : {', '.join(study.get('flashcards', []))}",
        "",
        "[3] TOMORROW MORNING'S PRIORITY APPLY QUEUE (8:00 AM BLOCK)",
        subsep,
    ]
    for idx, q in enumerate(tm_queue, 1):
        txt.append(f"  {idx:>2}. [{q.get('score', 0)}% Match | ATS {q.get('ats') or '-'}%] {q.get('title', '')} @ {q.get('company', '')} ({q.get('location', '')}) -> {q.get('url', '')}")

    if contests:
        txt += ["", "[4] ACTIVE HACKATHONS & HIRING CHALLENGES TO ENTER", subsep]
        for idx, c in enumerate(contests, 1):
            txt.append(f"  {idx:>2}. {c.get('title', '')} ({c.get('reward', '')}) -> {c.get('url', '')}")

    th_style = "padding:10px 12px;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#2E4352;background:#E6EFF6;border-bottom:2px solid #CBD5E1;"
    td_style = "padding:10px 12px;font-size:13px;color:#1E293B;border-bottom:1px solid #E2E8F0;vertical-align:top;"
    sec_title = "margin:22px 0 10px 0;padding-bottom:6px;border-bottom:2px solid #2E4352;color:#2E4352;font-size:16px;font-weight:700;"

    h = [
        '<html><body style="margin:0;padding:20px;background-color:#F5F2EB;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1E293B;">',
        '<div style="max-width:860px;margin:0 auto;background-color:#FCFBF9;border:1px solid #DDD6C7;border-radius:10px;overflow:hidden;">',
        '<div style="background-color:#2E4352;color:#FFFFFF;padding:20px 24px;">',
        '<div style="font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:#CBD5E1;margin-bottom:4px;">CAREER AGENT SYSTEM v6.5 • 7:00 PM IST EVENING REVIEW AGENT</div>',
        f'<h2 style="margin:0;font-size:20px;font-weight:700;color:#FFFFFF;">{e(head)}</h2>',
        '</div>',
        '<div style="padding:20px 24px;">',
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:18px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;"><tr>',
        f'<td style="padding:12px 16px;border-right:1px solid #E2E8F0;width:33%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Tracked Applications</div><div style="font-size:20px;font-weight:700;color:#2E4352;">{e(payload.get("applications_tracked", 0))}</div></td>',
        f'<td style="padding:12px 16px;border-right:1px solid #E2E8F0;width:33%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Ready Drafts &amp; PDFs</div><div style="font-size:20px;font-weight:700;color:#1E4E79;">{e(payload.get("drafts_ready", 0))} / {e(payload.get("resumes_ready", 0))}</div></td>',
        f'<td style="padding:12px 16px;width:34%;"><div style="font-size:11px;color:#64748B;text-transform:uppercase;">Bounced (Portal Needed)</div><div style="font-size:20px;font-weight:700;color:#B45309;">{e(payload.get("bounced_count", 0))}</div></td>',
        '</tr></table>',
        f'<h3 style="{sec_title}">1. Inbox, Bounce Alerts &amp; Application Status</h3>',
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">',
        f'<thead><tr><th style="{th_style}width:36%;">Role &amp; Company</th><th style="{th_style}width:24%;">Status</th><th style="{th_style}width:40%;">Next Step</th></tr></thead><tbody>',
    ]
    for jid, a in apps.items():
        h.append(
            f'<tr><td style="{td_style}">{link(a.get("url", ""), a.get("title", ""))}<div style="font-size:12px;color:#475569;"><b>{e(a.get("company", ""))}</b></div></td>'
            f'<td style="{td_style}font-size:12px;"><span style="background:#EFECE6;color:#2E4352;padding:2px 6px;border-radius:4px;font-weight:600;">{e(a.get("status", ""))}</span></td>'
            f'<td style="{td_style}font-size:12px;">{e(a.get("note") or "Monitor inbox or submit on portal")}</td></tr>'
        )
    h.append('</tbody></table>')

    h.append(f'<h3 style="{sec_title}">2. Tonight&#39;s 6:30 PM DSA &amp; 9:00 PM Certification Study Session</h3>')
    h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
    h.append(f'<thead><tr><th style="{th_style}width:30%;">Block</th><th style="{th_style}width:70%;">Assigned Module &amp; Practice Task</th></tr></thead><tbody>')
    h.append(f'<tr><td style="{td_style}font-weight:600;color:#2E4352;">06:30 PM DSA Block</td><td style="{td_style}">{e(study.get("dsa_630pm", ""))}</td></tr>')
    h.append(f'<tr><td style="{td_style}font-weight:600;color:#2E4352;">09:00 PM Certification</td><td style="{td_style}">{e(study.get("cert_900pm", ""))}</td></tr>')
    h.append(f'<tr><td style="{td_style}font-weight:600;color:#2E4352;">Hands-On Coding Task</td><td style="{td_style}">{e(study.get("hands_on_task", ""))}</td></tr>')
    h.append(f'<tr><td style="{td_style}font-weight:600;color:#2E4352;">Flashcard Review</td><td style="{td_style}font-family:monospace;">{e(", ".join(study.get("flashcards", [])))}</td></tr>')
    h.append('</tbody></table>')

    h.append(f'<h3 style="{sec_title}">3. Tomorrow Morning&#39;s Priority Apply Queue</h3>')
    h.append('<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #E2E8F0;">')
    h.append(f'<thead><tr><th style="{th_style}width:18%;">Match / ATS</th><th style="{th_style}width:52%;">Role &amp; Company</th><th style="{th_style}width:30%;">Location &amp; Portal</th></tr></thead><tbody>')
    for q in tm_queue:
        h.append(
            f'<tr><td style="{td_style}"><span style="background:#E3EFE8;color:#1E6F50;padding:2px 6px;border-radius:4px;font-weight:700;font-size:12px;">{e(q.get("score", 0))}% Match</span></td>'
            f'<td style="{td_style}">{link(q.get("url", ""), q.get("title", ""))} — <b>{e(q.get("company", ""))}</b></td>'
            f'<td style="{td_style}font-size:12px;">{e(q.get("location", "Remote"))}</td></tr>'
        )
    h.append('</tbody></table>')
    h.append('</div></div></body></html>')
    return "\n".join(txt), "\n".join(h)
