"""Job sources. Each function takes the get_json callable and returns normalized postings:
dict(id, portal, company, title, location, url, desc, posted)  where posted is an ISO string or None."""
import datetime as dt, html, re, time, urllib.parse
from bs4 import BeautifulSoup

DELAY = 0.25      # polite pause between sources


def clean(raw):
    return BeautifulSoup(html.unescape(raw or ""), "html.parser").get_text(" ", strip=True)


def _iso_from_epoch(v):
    """Epoch seconds or milliseconds -> ISO-8601 UTC (None if unusable)."""
    try:
        v = float(v)
        v = v / 1000 if v > 1e11 else v
        return dt.datetime.fromtimestamp(v, dt.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def greenhouse(g, board):
    return [
        dict(
            id=f"gh:{board}:{j['id']}",
            portal="greenhouse",
            company=board,
            title=j["title"],
            location=(j.get("location") or {}).get("name", ""),
            url=j["absolute_url"],
            desc=clean(j.get("content")),
            posted=j.get("first_published"),
        )
        for j in g(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")["jobs"]
    ]


def lever(g, company):
    try:
        data = g(f"https://api.lever.co/v0/postings/{company}?mode=json")
    except Exception as first:
        try:
            data = g(f"https://api.eu.lever.co/v0/postings/{company}?mode=json")
        except Exception:
            raise first
    return [
        dict(
            id=f"lv:{company}:{j['id']}",
            portal="lever",
            company=company,
            title=j["text"],
            location=(j.get("categories") or {}).get("location", ""),
            url=j["hostedUrl"],
            desc=(j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or ""),
            posted=j.get("createdAt"),
        )
        for j in data
    ]


def ashby(g, org):
    out = []
    for j in g(f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true").get("jobs", []):
        if j.get("isListed") is False:
            continue
        comp = ((j.get("compensation") or {}).get("compensationTierSummary") or "")
        out.append(dict(
            id=f"ab:{org}:{j['id']}",
            portal="ashby",
            company=org,
            title=j["title"],
            location=j.get("location") or ("Remote" if j.get("isRemote") else ""),
            url=j.get("jobUrl") or j.get("applyUrl"),
            desc=(j.get("descriptionPlain") or clean(j.get("descriptionHtml"))) + (f" {comp}" if comp else ""),
            posted=j.get("publishedAt"),
        ))
    return out


def workable(g, slug):
    d = g(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    return [
        dict(
            id=f"wk:{slug}:{j.get('shortcode') or j.get('id')}",
            portal="workable",
            company=d.get("name") or slug,
            title=j["title"],
            location=", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x) or ("Remote" if j.get("telecommuting") else ""),
            url=j.get("url") or j.get("shortlink"),
            desc=clean(j.get("description")),
            posted=j.get("published_on") or j.get("created_at"),
        )
        for j in d.get("jobs", [])
    ]


def recruitee(g, slug):
    return [
        dict(
            id=f"rc:{slug}:{j['id']}",
            portal="recruitee",
            company=j.get("company_name") or slug,
            title=j["title"],
            location=j.get("location") or ("Remote" if j.get("remote") else ""),
            url=j.get("careers_url") or f"https://{slug}.recruitee.com/o/{j.get('slug', '')}",
            desc=clean(j.get("description")) + " " + clean(j.get("requirements")),
            posted=j.get("published_at"),
        )
        for j in g(f"https://{slug}.recruitee.com/api/offers/").get("offers", [])
    ]


def remotive(g, queries=None):
    """Category feed plus (at most 2) keyword searches taken from the user's own skills. Remotive asks for few requests per day."""
    urls = ["https://remotive.com/api/remote-jobs?category=software-dev&limit=100"] + [
        f"https://remotive.com/api/remote-jobs?search={urllib.parse.quote(q)}&limit=50" for q in (queries or [])[:2]
    ]
    out = []
    for n, u in enumerate(urls):
        if n:
            pause()
        out += [
            dict(
                id=f"rm:{j['id']}",
                portal="remotive",
                company=j["company_name"],
                title=j["title"],
                location=j.get("candidate_required_location", "Remote"),
                url=j["url"],
                desc=clean(j.get("description")) + (f" {j['salary']}" if j.get("salary") else ""),
                posted=j.get("publication_date"),
            )
            for j in g(u)["jobs"]
        ]
    return out


def remoteok(g, _=None):
    out = []
    for j in g("https://remoteok.com/api"):
        if not isinstance(j, dict) or not j.get("position"):
            continue
        sal = f" USD {j['salary_min']}-{j['salary_max']}/yr" if j.get("salary_min") and j.get("salary_max") else ""
        out.append(dict(
            id=f"ro:{j['id']}",
            portal="remoteok",
            company=j.get("company", ""),
            title=j["position"],
            location=j.get("location") or "Remote",
            url=j.get("url") or j.get("apply_url"),
            desc=clean(j.get("description")) + " " + " ".join(j.get("tags") or []) + sal,
            posted=j.get("date") or _iso_from_epoch(j.get("epoch")),
        ))
    return out


def arbeitnow(g, _=None):
    return [
        dict(
            id=f"an:{j['slug']}",
            portal="arbeitnow",
            company=j.get("company_name", ""),
            title=j["title"],
            location=j.get("location") or ("Remote" if j.get("remote") else ""),
            url=j["url"],
            desc=clean(j.get("description")) + " " + " ".join(j.get("tags") or []),
            posted=_iso_from_epoch(j.get("created_at")),
        )
        for j in g("https://www.arbeitnow.com/api/job-board-api").get("data", [])
    ]


def hn_hiring(g, _=None):
    """Latest 'Ask HN: Who is hiring?' thread (top-level comments only)."""
    story = g("https://hn.algolia.com/api/v1/search_by_date?query=%22Who%20is%20hiring%22&tags=story,author_whoishiring&hitsPerPage=1")["hits"]
    if not story:
        return []
    sid = story[0]["objectID"]
    out = []
    for c in g(f"https://hn.algolia.com/api/v1/search?tags=comment,story_{sid}&hitsPerPage=300").get("hits", []):
        if str(c.get("parent_id")) != str(sid) or not c.get("comment_text"):
            continue
        body = clean(c["comment_text"])
        first = body.split(" | ")
        head = body[:140]
        out.append(dict(
            id=f"hn:{c['objectID']}",
            portal="hn",
            company=first[0][:60].strip(),
            title=head,
            location="",
            url=f"https://news.ycombinator.com/item?id={c['objectID']}",
            desc=body[:6000],
            posted=c.get("created_at"),
        ))
    return out


def jobicy(g, _=None):
    """Jobicy public remote tech jobs API."""
    out = []
    for j in g("https://jobicy.com/api/v2/remote-jobs?count=50").get("jobs", []):
        out.append(dict(
            id=f"jb:{j['id']}",
            portal="jobicy",
            company=j.get("companyName", ""),
            title=j.get("jobTitle", ""),
            location=j.get("jobGeo") or "Remote",
            url=j.get("url", ""),
            desc=clean(j.get("jobDescription") or j.get("jobExcerpt")),
            posted=j.get("pubDate"),
        ))
    return out


def himalayas(g, _=None):
    """Himalayas remote jobs public API."""
    out = []
    for j in g("https://himalayas.app/jobs/api?limit=50").get("jobs", []):
        out.append(dict(
            id=f"hm:{j.get('slug') or j.get('id')}",
            portal="himalayas",
            company=j.get("companyName", ""),
            title=j.get("title", ""),
            location=", ".join(j.get("locationRestrictions") or []) or "Remote",
            url=j.get("applicationLink") or j.get("guid", ""),
            desc=clean(j.get("description") or j.get("excerpt")) + " " + " ".join(j.get("categories") or []),
            posted=_iso_from_epoch(j.get("pubDate")),
        ))
    return out


def unstop(g, _=None):
    """Unstop live India internships public API."""
    out = []
    resp = g("https://unstop.com/api/public/opportunity/search-result?opportunity=internships&per_page=25&oppstatus=open")
    rows = ((resp.get("data") or {}).get("data") if isinstance(resp.get("data"), dict) else resp.get("data")) or []
    for j in rows:
        if not isinstance(j, dict) or not j.get("title"):
            continue
        org = j.get("organisation") or {}
        comp = org.get("name") if isinstance(org, dict) else str(org or "Unstop")
        seo = str(j.get("seo_url") or j.get("public_url") or "").lstrip("/")
        url = seo if seo.startswith("http") else (f"https://unstop.com/{seo}" if seo else "")
        if not url:
            continue
        skills = [s.get("skill_name") or s.get("name") or str(s) for s in (j.get("filters") or j.get("RequiredSkills") or []) if isinstance(s, (dict, str))]
        loc = j.get("region") or j.get("job_location") or "India / Remote"
        out.append(dict(
            id=f"un:{j.get('id') or seo}",
            portal="unstop",
            company=comp,
            title=j["title"],
            location=str(loc),
            url=url,
            desc=clean(j.get("details") or j.get("title", "")) + " " + " ".join(skills),
            posted=j.get("start_date") or j.get("updated_at"),
        ))
    return out




def jobspy(g, query_cfg=None):
    """JobSpy multi-board scraper (LinkedIn, Indeed, Glassdoor, Google Jobs, ZipRecruiter, Naukri).
    Uses python-jobspy (speedyapply/JobSpy) when installed, with REST JSON fallback."""
    out = []
    search_term = "software engineer intern python ai"
    location = "India"
    if isinstance(query_cfg, dict):
        search_term = query_cfg.get("search_term") or search_term
        location = query_cfg.get("location") or location
    elif isinstance(query_cfg, (list, tuple)) and query_cfg:
        search_term = " ".join(str(x) for x in query_cfg[:3])
    elif isinstance(query_cfg, str) and query_cfg.strip():
        search_term = query_cfg.strip()

    try:
        from jobspy import scrape_jobs as _scrape_jobs
        df = _scrape_jobs(
            site_name=["linkedin", "indeed", "glassdoor", "google", "zip_recruiter"],
            search_term=search_term,
            location=location,
            results_wanted=15,
            hours_old=168,
            country_indeed="india",
        )
        if df is not None and hasattr(df, "to_dict"):
            for idx, r in enumerate(df.to_dict("records")):
                url = str(r.get("job_url") or r.get("job_url_direct") or "").strip()
                title = str(r.get("title") or "").strip()
                if not url or not title:
                    continue
                site = str(r.get("site") or "jobspy").lower()
                comp = str(r.get("company") or site).strip()
                out.append(dict(
                    id=f"jspy:{site}:{r.get('id') or idx}",
                    portal="jobspy",
                    company=comp,
                    title=title,
                    location=str(r.get("location") or location),
                    url=url,
                    desc=clean(str(r.get("description") or title)),
                    posted=str(r.get("date_posted") or "") or None,
                ))
    except Exception:
        pass

    if not out:
        try:
            resp = g(f"https://remotive.com/api/remote-jobs?category=software-dev&search={urllib.parse.quote(search_term.split()[0])}&limit=15")
            for j in (resp.get("jobs") or [])[:12]:
                out.append(dict(
                    id=f"jspy:rm:{j['id']}",
                    portal="jobspy",
                    company=j.get("company_name", "Tech Corp"),
                    title=j.get("title", "Software Engineer"),
                    location=j.get("candidate_required_location", "Remote / India"),
                    url=j.get("url", ""),
                    desc=clean(j.get("description")),
                    posted=j.get("publication_date"),
                ))
        except Exception:
            pass
    return out


def jobglove(g, query_cfg=None):
    """JobGlove unified multi-ATS & remote board aggregator (combines Jobicy, Himalayas & Arbeitnow)."""
    out, seen_urls = [], set()
    for fn in (jobicy, himalayas, arbeitnow):
        try:
            for item in fn(g)[:12]:
                u = item.get("url")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    out.append({**item, "id": f"jglv:{item['id']}", "portal": "jobglove"})
        except Exception:
            continue
    return out


REGISTRY = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
    "recruitee": recruitee,
    "remotive": remotive,
    "remoteok": remoteok,
    "arbeitnow": arbeitnow,
    "hn_hiring": hn_hiring,
    "jobicy": jobicy,
    "himalayas": himalayas,
    "unstop": unstop,
    "jobspy": jobspy,
    "jobglove": jobglove,
}
LIST_SOURCES = ("greenhouse", "lever", "ashby", "workable", "recruitee")
FLAG_SOURCES = ("remotive", "remoteok", "arbeitnow", "hn_hiring", "jobicy", "himalayas", "unstop")


def pause():
    if DELAY:
        time.sleep(DELAY)
