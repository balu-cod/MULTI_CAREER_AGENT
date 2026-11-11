# MULTI_CAREER_AGENT

> NEED JOB! USE MCA.....!!!!!!!!!!!

# Career Agent System v6.5.0

Personal, human-in-the-loop job-search assistant. One codebase: the `live/` package on top of one `VaultAgent`.

```
pip install -r requirements.txt            # playwright install chromium (only for apply)
cp private.example.profile.json private/profile.json   # your contact details; git-ignored
python career_agent_system.py --mode live-pipeline     # scan, score, draft, report
python career_agent_system.py --mode apply             # DRY RUN
python career_agent_system.py --mode apply --submit    # asks y/n per job
python career_agent_system.py --mode scrub-private     # move contact details out of the committed Vault
python career_agent_system.py --mode import-profile --file my_profile.json   # load projects/experience/skills into the Vault (see profile.example.json)
python career_agent_system.py --mode build-resume                            # base resume PDF from the Vault, no scanning
python career_agent_system.py --mode build-resume --job job.txt              # tailored to a pasted job description (or a .txt path)
python -m unittest discover -s tests -t .
```

## Real data sources
Edit `job_sources` in `vault/user_profile_v1.json`: `greenhouse`, `lever`, `ashby`, `workable` take lists of company slugs (the part of the careers URL, e.g. `boards.greenhouse.io/<slug>`); `remotive`, `remoteok`, `arbeitnow`, `hn_hiring` are true/false; `pages` takes careers-page URLs.
`python career_agent_system.py --mode check-sources` prints a per-source health table. A wrong slug shows as `BAD ... 404` and never stops the other sources. The daily workflow runs with `--strict`, so it fails if nothing was fetched or any source errored.

## Resume generator (built from the Vault)
Every resume is assembled from your Vault profile; nothing is invented. Fill in `profile.example.json` (copy it, edit it, then run `--mode import-profile --file my_profile.json`; contact details are split into git-ignored `private/profile.json` automatically). Fields: `technical_skills`, optional `skill_groups`, `experience[]` (role, company, period, bullets, skills), `projects[]` (name, link, bullets, skills), `education`, `certifications`, `achievements`, `summary`, `github`, `linkedin`, `portfolio`, `location`.
- **Tailoring per job:** the most relevant projects and bullets come first, skills the job mentions lead each skill group, and the rest is trimmed to fit.
- **One page, ATS-friendly:** single column, standard headings, real text. The font shrinks from 10 to 8 pt, then the least relevant items are dropped, until it fits one page.
- **Truthful:** skills listed = Vault skills only. A Claude-written summary is discarded (a plain Vault-based one is used) if it names a technology or a number that is not in your Vault. `private/tailored/*.md` lists what the job asks for that you do NOT have ("do not claim").
- **Outputs:** `private/resumes/<job>.pdf` per top job, `private/resumes/_base.pdf` (used by the applier when `private/resume.pdf` is missing), and `private/tailored/<job>.md`. Cold-email drafts also mention your most relevant project.
- The Vault is checksummed: edit it with `import-profile`, not by hand. `experience`/`projects` live in the committed `vault/user_profile_v1.json`, so keep them to what you are happy to show if the repo is public.

## Scraping and browsing
- **Parallel:** all sources are fetched at once (`job_sources.workers`, default 6, max 12) with a per-host pause, pooled connections, retries with `Retry-After`, and a timeout on `robots.txt` (the old fetch could hang there). One failing source never stops the others; `check-sources` shows time per source.
- **Careers pages (`pages`)** accept a URL or `{"url": ..., "company": ..., "limit": 40, "pages": 3, "render": false}`. In order: (1) an embedded Greenhouse/Lever/Ashby/Workable/Recruitee board is detected and its real API is used (so those jobs also work with the applier); (2) schema.org JobPosting JSON-LD (expired postings skipped); (3) cleaned page text of each job-looking link, with navigation, files and off-site links filtered, `rel=next` pagination followed, and job pages fetched in parallel.
- **JavaScript-only pages:** set `"render": true`, or leave it off and it is tried automatically when a static page shows nothing. Needs `playwright install chromium`; without it that page just reports no postings.
- **New:** `recruitee` slugs; Lever EU accounts are retried on `api.eu.lever.co`; duplicates are removed by canonical URL (tracking parameters ignored) as well as by id.
- Respects `robots.txt` and never bypasses logins or CAPTCHAs.

## Dynamic data and per-run memory
Every run fetches fresh data and analyses it against your Vault profile:
- **Jobs:** all configured sources are re-fetched. Remotive is also searched with your top 2 skills (override with `remotive_queries`).
- **Learning/certifications:** the Microsoft Learn catalog API, a community free-certification list and `live/cert_catalog.json` are fetched live, filtered to your gaps, interests and level (beginner for interns/freshers), then URL-checked. Each pick carries a `free_claim` that says what is and is not free; confirm on the provider page before relying on it.
- **Memory:** each run writes `vault/memory/run_<UTC id>.json` (full record) and `.md` (readable summary), plus `index.json` and `latest.json`. It records your skill analysis, matched jobs, which jobs and learning picks are new since the last run, source health, errors and a redacted run log. Contact details are never included. The newest `memory_keep` runs (default 90) are kept; the workflow commits the folder so memory persists between daily runs.

## YouTube news and tech sections
The `youtube` agent writes `vault/youtube_updates_v1.json`; the dashboard shows it as two card grids (**Tech & AI news**, last 4 days; **Tech content**, last 14 days) and the digest email includes both.
Edit `youtube` in `vault/user_profile_v1.json`: per section, `channels` takes `@handles` or `UC...` ids, `max_age_days` sets freshness. Channel feeds need no API key. Optional: set `YOUTUBE_API_KEY` and add `queries` (e.g. `"AI agents"`) to also search for new videos by topic. Shorts and future-dated items are dropped. A wrong handle appears as a "Channels with problems" line on the dashboard and in the digest; if every source fails, yesterday's videos stay on the dashboard.

## Gmail setup (sending and reading)
1. Use a separate Gmail account. Turn on 2-Step Verification, then create an App Password (16 characters).
2. Set `GMAIL_SMTP_USER` and `GMAIL_SMTP_APP_PASSWORD` (environment variables locally, repo secrets in Actions). Also enable IMAP in Gmail settings for the inbox reader.
3. `python career_agent_system.py --mode test-mail` sends one test message to `contact_email`.
4. Daily digest (HTML + text) is sent by the pipeline. Drafts for cold emails and follow-ups appear in `private/drafts/` and `private/followups/` with an empty `To:` line (follow-ups prefill it from the recruiter's reply). Fill in `To:`, then run `--mode send-mail`; it shows each email and sends only on a typed `y`, attaching the tailored resume PDF. Sent drafts move to `private/sent/`. Use `--dry-run` to rehearse.
5. Safeguards: address validation, header-injection check, retries on dropped connections, a daily cap (40), and every send logged in `private/audit.log`.

## Privacy model
- `vault/*.json` holds only non-sensitive config and results. Phone, email, education/roll/rank, LinkedIn live in `private/profile.json` (git-ignored). In CI they come from the `PROFILE_JSON` secret.
- The workflow commits an explicit file allowlist. There is no `git add -f`.
- Every apply/submit action is appended to `private/audit.log`.
- Job descriptions are wrapped as untrusted data in LLM prompts.
- `new-agent` plugins: import allowlist (`re, json, datetime, requests`), saved disabled until you review them.

## Purging history
Old commits may still contain your phone number. Rotate/accept that, or rewrite history with `git filter-repo --replace-text`, then force-push and make the repo private.

## Apply safety
`APPLY_MODE=off|dry-run|submit`. Submit needs `APPLY_CONFIRM=I_APPROVE`, a resume attached, and no empty required fields; otherwise the job is marked `needs_human_form`. CAPTCHAs are left to you.

## User data backend & Google sign-in (v7.8)
`live/user_data_backend.py` stores candidate profile, applications, contacts, Gmail headers and OAuth sessions in `private/user_data.db`.
Three new modules add the full OAuth 2.0 flow: `live/oauth_google.py` (PKCE + token exchange), `live/gmail_api.py` (Gmail REST API), `live/accounts.py` (sessions + token storage).
`USERDATA_REQUIRE_AUTH=1` demands `Authorization: Bearer <session_token>` on `/api/userdata/*`. `USERDATA_DEV_AUTH=1` allows unverified local sign-in (development only).
Run alone: `--mode user-backend --port 8001`; or inside `--mode serve`.

## Testing the whole system
`python test_career_agent_system.py` runs every test, including `tests/test_e2e.py`, which copies the project to a temp dir and drives the real CLI modes
(import-profile, build-resume, live-pipeline offline, --strict), the main server, the standalone user backend, OAuth, required-auth, path-traversal checks and a personal-data scan.

## Sign-in setup (Google + Gmail) — v7.9

### Option A — Continue with Google (OAuth 2.0 full flow, recommended)
Grants real Gmail API read + send access. No App Password needed.

1. **Google Cloud Console** → APIs & Services → Credentials → *Create credentials → OAuth client ID → Web application*.
2. Under **Authorised redirect URIs** add: `http://localhost:<port>/api/auth/google/callback`
   (replace `<port>` with the port printed by `--mode serve`; keep it consistent).
3. Download the client, then set both keys:
   ```
   python career_agent_system.py --set-key GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
   python career_agent_system.py --set-key GOOGLE_CLIENT_SECRET=<secret>
   ```
4. Enable the **Gmail API**: APIs & Services → Library → Gmail API → Enable.
5. While the OAuth consent screen is in *Testing*, add your Gmail address under **Test users**.
6. Restart and open `http://localhost:<port>`. Click **Continue with Google** — the browser is redirected to Google, you approve access, and you're signed in with Gmail read + send ready.

The flow uses **PKCE** (S256) so the client secret never touches the browser. Sessions are stored in an `HttpOnly` cookie (`cas_session`). Tokens are stored hashed in `private/user_data.db`.

### Option B — Gmail App Password (IMAP, no Google Cloud setup required)
1. Turn on 2-Step Verification on your Gmail account.
2. Create an App Password (Google Account → Security → App Passwords) — 16 characters.
3. Enter your Gmail address and the App Password in the sign-in form.
   The server authenticates against `imap.gmail.com` before accepting it.
   Credentials are saved to `.env/` only after Gmail accepts them.

Both options can coexist: the OAuth flow is used when tokens are present; IMAP is the fallback.

- Sign-out revokes the session server-side. The old cookie immediately becomes invalid.
- Every page loads `js/auth.js`; edit sign-in behaviour there once.
