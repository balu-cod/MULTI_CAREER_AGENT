"""Careers-page scraping. Tries, in order of data quality:
 1. an embedded ATS board (Greenhouse/Lever/Ashby/Workable/Recruitee) -> use that board's real API
 2. schema.org JobPosting JSON-LD on the listing or on each job page
 3. cleaned page text of each job-looking link (nav/footer/scripts removed)
Static HTML is tried first; Playwright rendering is optional (entry {"url": ..., "render": true}, or automatic when a static page shows nothing)."""
import datetime as dt, json, re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from bs4 import BeautifulSoup
from . import sources as S

ATS_PATTERNS = (
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?(?:[^\"'\s]*&)?for=([\w-]+)", re.I)),
    ("lever", re.compile(r"jobs(?:\.eu)?\.lever\.co/([\w-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w.%-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([\w-]+)", re.I)),
    ("recruitee", re.compile(r"([\w-]+)\.recruitee\.com", re.I)),
)
NOT_SLUGS = {"embed", "embed_job_board", "v1", "js", "api", "www", "app", "help", "status", "static", "assets"}
DEFAULT_KEYWORDS = ("intern", "engineer", "developer", "software", "backend", "back-end", "frontend", "front-end", "full stack", "full-stack", "data", "ai ", "ml ",
                    "analyst", "trainee", "graduate", "programmer", "devops", "sde", "python")
JOB_HREF = re.compile(r"/(?:jobs?|careers?|positions?|openings?|vacanc\w*|opportunit\w*|roles?|postings?|requisitions?)/[^/?#]+", re.I)
SKIP_HREF = re.compile(r"^(?:mailto:|tel:|javascript:|#)|\.(?:pdf|png|jpe?g|gif|svg|zip|docx?|css|js)(?:\?|$)", re.I)
NAV_TEXT = {"careers", "jobs", "home", "about", "contact", "benefits", "culture", "teams", "locations", "all jobs", "see all jobs", "view all jobs", "open positions", "back"}


def canon(url):
    """Canonical URL for de-duplication: lowercase host, no fragment, no utm/tracking params, no trailing slash."""
    try:
        u = urlparse(str(url).strip()); q = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith(("utm_", "ref", "src", "gh_src", "source", "fbclid", "gclid"))]
        return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path.rstrip("/") or "/", "", urlencode(q), ""))
    except ValueError:
        return str(url)


def detect_ats(html_text):
    """[(kind, slug)] for every known job board referenced by the page (links, iframes, script embeds)."""
    found = []
    for kind, rx in ATS_PATTERNS:
        for m in rx.finditer(html_text or ""):
            slug = m.group(1)
            if slug.lower() in NOT_SLUGS or (kind, slug) in found: continue
            found.append((kind, slug))
    return found[:3]


def _nodes(data):
    if isinstance(data, list):
        for x in data: yield from _nodes(x)
    elif isinstance(data, dict):
        yield data
        for x in (data.get("@graph") or []): yield from _nodes(x)


def _loc(node):
    out = []
    for l in (node.get("jobLocation") if isinstance(node.get("jobLocation"), list) else [node.get("jobLocation")]):
        a = (l or {}).get("address") if isinstance(l, dict) else None
        if isinstance(a, dict):
            c = a.get("addressCountry"); c = c.get("name") if isinstance(c, dict) else c
            out.append(", ".join(str(x) for x in (a.get("addressLocality"), a.get("addressRegion"), c) if x))
        elif isinstance(a, str): out.append(a)
    if str(node.get("jobLocationType", "")).upper() == "TELECOMMUTE": out.append("Remote")
    return "; ".join(x for x in out if x)


def _expired(v):
    try:
        d = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")[:25])
        return d.date() < dt.date.today()
    except ValueError: return False


def jsonld_jobs(soup, base_url):
    """schema.org JobPosting blocks -> normalized postings (expired ones dropped)."""
    out = []
    for tag in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        try: data = json.loads(tag.string or tag.get_text() or "", strict=False)
        except ValueError: continue
        for n in _nodes(data):
            t = n.get("@type"); t = t if isinstance(t, list) else [t]
            if "JobPosting" not in t or not n.get("title") or _expired(n.get("validThrough")): continue
            org = n.get("hiringOrganization"); org = org.get("name") if isinstance(org, dict) else org
            sal = n.get("baseSalary"); val = sal.get("value") if isinstance(sal, dict) else None
            pay = f" {sal.get('currency', '')} {val.get('minValue', '')}-{val.get('maxValue', '')}".replace(" -", "") if isinstance(val, dict) and (val.get("minValue") or val.get("maxValue")) else ""
            url = urljoin(base_url, n.get("url") or n.get("sameAs") or base_url)
            out.append(dict(id=f"pg:{canon(url)}", portal="page", company=str(org or "").strip(), title=S.clean(str(n["title"])), location=_loc(n), url=url,
                            desc=(S.clean(n.get("description")) + pay)[:8000], posted=n.get("datePosted")))
    return out


def page_text(soup, sep=" "):
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg", "iframe", "aside"]): t.decompose()
    node = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup
    return node.get_text(sep, strip=True)


def _meta(soup, *names):
    for n in names:
        t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n}) or soup.find("meta", attrs={"itemprop": n})
        if t and t.get("content"): return t["content"].strip()
    return ""


def plain_job(soup, url, keywords, company=""):
    """Fallback for pages with no JSON-LD: title from h1/og:title, text from the main content, light location/date heuristics."""
    h1 = soup.find("h1"); title = (h1.get_text(" ", strip=True) if h1 else "") or _meta(soup, "og:title") or (soup.title.get_text(strip=True) if soup.title else "")
    posted = _meta(soup, "article:published_time", "datePosted", "datePublished") or next((t["datetime"] for t in soup.find_all("time", datetime=True)), None)
    site = _meta(soup, "og:site_name"); lines = page_text(soup, "\n").splitlines(); text = " ".join(" ".join(lines).split())
    if len(text) < 200 or not title or not any(k in (title + " " + text[:600]).lower() for k in keywords): return None
    loc = ""
    for n, ln in enumerate(lines[:80]):                                     # "Location: Pune" on one line, or a "Location" label followed by its value
        m = re.match(r"(?i)^(?:job\s+)?locations?\s*[:\-]?\s*(.*)$", ln)
        if m: loc = (m.group(1) or (lines[n + 1] if n + 1 < len(lines) else "")).strip()[:60]; break
    loc = loc or ("Remote" if re.search(r"\bremote\b", text[:600], re.I) else "")
    return dict(id=f"pg:{canon(url)}", portal="page", company=company or site or urlparse(url).netloc.removeprefix("www."), title=title[:140], location=loc, url=url, desc=text[:6000], posted=posted or None)


def job_links(soup, base_url, keywords):
    """Ranked, de-duplicated candidate job links on a listing page (same site only; nav and file links skipped)."""
    host = urlparse(base_url).netloc.removeprefix("www."); site = ".".join(host.split(".")[-2:]); seen, scored = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if SKIP_HREF.search(href): continue
        link = urljoin(base_url, href); u = urlparse(link); text = a.get_text(" ", strip=True)
        if u.scheme not in ("http", "https") or not (u.netloc.removeprefix("www.") == host or u.netloc.endswith("." + site)): continue
        key = canon(link)
        if key in seen or key == canon(base_url) or text.lower() in NAV_TEXT: continue
        score = (2 if any(k in text.lower() + " " for k in keywords) else 0) + (1 if JOB_HREF.search(u.path) else 0)
        if score: seen.add(key); scored.append((-score, len(scored), link))
    return [l for _, _, l in sorted(scored)]


def next_page(soup, base_url):
    a = soup.find("a", rel=lambda r: r and "next" in r, href=True) or soup.find("link", rel="next", href=True) or next(
        (x for x in soup.find_all("a", href=True) if x.get_text(" ", strip=True).lower() in ("next", "next page", "next ›", "›", "»") or "next" in (x.get("aria-label") or "").lower()), None)
    return urljoin(base_url, a["href"]) if a else None


def render_html(url, timeout_ms=45000):
    """Optional JavaScript rendering with Playwright (the same Chromium the applier uses). None if Playwright is not installed or the page fails."""
    try: from playwright.sync_api import sync_playwright
    except ImportError: return None
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            try: pg = br.new_page(); pg.goto(url, timeout=timeout_ms, wait_until="networkidle"); return pg.content()
            finally: br.close()
    except Exception: return None


def scrape_page(entry, get_json, fetch, allowed=lambda u: True, render=render_html, keywords=DEFAULT_KEYWORDS, workers=4, log=lambda m: None):
    """entry: URL string or {"url", "render": bool, "limit": int, "company": str, "pages": int}. Returns normalized postings."""
    cfg = {"url": entry} if isinstance(entry, str) else dict(entry); url = cfg["url"]; limit = int(cfg.get("limit", 40)); max_pages = int(cfg.get("pages", 3))
    keywords = tuple(k.lower() for k in keywords)
    html_ = render(url) if cfg.get("render") else fetch(url)
    if not html_: raise RuntimeError("page unavailable (disallowed by robots.txt, missing, or blocked)")
    for kind, slug in detect_ats(html_):                                    # 1. a real job-board API beats scraping HTML
        try:
            found = S.REGISTRY[kind](get_json, slug)
            if found: log(f"  {url}: uses {kind} board '{slug}' ({len(found)} postings)"); return found
        except Exception as e: log(f"  {url}: {kind} board '{slug}' failed ({str(e)[:80]}); scraping the page instead")
    out, seen_pages, links, page_url = [], set(), [], url
    for _ in range(max_pages):                                              # 2. listing pages (follow rel=next)
        seen_pages.add(canon(page_url)); soup = BeautifulSoup(html_, "html.parser")
        ld = jsonld_jobs(soup, page_url); out += ld
        if not ld: links += [l for l in job_links(soup, page_url, keywords) if l not in links]
        nxt = next_page(soup, page_url)
        if not nxt or canon(nxt) in seen_pages or len(links) + len(out) >= limit: break
        html_ = fetch(nxt)
        if not html_: break
        page_url = nxt
    if not out and not links and not cfg.get("render"):                      # JS-only page: try one rendered pass
        rendered = render(url)
        if rendered:
            soup = BeautifulSoup(rendered, "html.parser"); out += jsonld_jobs(soup, url); links = job_links(soup, url, keywords)
    known = {canon(j["url"]) for j in out}; links = [l for l in links if canon(l) not in known][:max(0, limit - len(out))]

    def one(link):                                                          # 3. each job page: JSON-LD first, plain text otherwise
        try:
            if not allowed(link): return []
            body = fetch(link)
            if not body: return []
            soup = BeautifulSoup(body, "html.parser"); ld = jsonld_jobs(soup, link)
            if ld: return ld[:1]
            j = plain_job(soup, link, keywords, cfg.get("company", "")); return [j] if j else []
        except Exception: return []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for r in ex.map(one, links): out += r
    host = urlparse(url).netloc.removeprefix("www.")
    for j in out: j["company"] = cfg.get("company") or j.get("company") or host
    seen, uniq = set(), []
    for j in out:
        k = canon(j["url"])
        if k not in seen: seen.add(k); uniq.append(j)
    return uniq[:limit]
