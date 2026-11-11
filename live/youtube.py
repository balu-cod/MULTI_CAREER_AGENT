"""Newest YouTube videos for two dashboard sections: News (AI/tech news) and Tech (tutorials, deep dives).
Primary source: each channel's public Atom feed (no API key). Optional: YouTube Data API search when YOUTUBE_API_KEY is set."""
import datetime as dt, html, re, urllib.parse
import xml.etree.ElementTree as ET

NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "m": "http://search.yahoo.com/mrss/"}
DEFAULTS = {
    "news": {"channels": ["@Fireship", "@aiexplained-official", "@mreflow"], "queries": [], "max_age_days": 14},
    "tech": {"channels": ["@freecodecamp", "@TechWorldwithNana", "@ArjanCodes", "@ThePrimeagen", "@CodeWithHarry"], "queries": [], "max_age_days": 21},
    "per_channel": 3, "limit": 12,
}
KNOWN_CHANNEL_IDS = {
    "@Fireship": "UCsBjURrPoezykLs9EqgamOA",
    "@aiexplained-official": "UCNJ1Ymd5yFuUPtn21xtRbbw",
    "@mreflow": "UC4JX40jDee_tINbkjycV4Sg",
    "@freecodecamp": "UC8butISFwT-Wl7EV0hUK0BQ",
    "@TechWorldwithNana": "UCdngmbVKX1Tgre699-XLlUA",
    "@ArjanCodes": "UCVhQ2NnY5Rskt6UjCUkJ_DA",
    "@ThePrimeagen": "UC8ENHE5xdFSwx71u3fDH5Xw",
    "@CodeWithHarry": "UCeVMnSShP_Iviwkknt83cww",
}
CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
FEED_LINK = re.compile(r"feeds/videos\.xml\?channel_id=(UC[A-Za-z0-9_-]{22})")
CANON = re.compile(r"youtube\.com/channel/(UC[A-Za-z0-9_-]{22})")


def age_hours(iso, now=None):
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return ((now or dt.datetime.now(dt.timezone.utc)) - d).total_seconds() / 3600
    except Exception:
        return None


def resolve_channel(ref, get_text, resolved):
    """'UC...' id -> itself; '@handle' -> channel id (resolved from page HTML or canonical map)."""
    ref = ref.strip()
    if CHANNEL_ID.match(ref):
        return ref
    if ref in resolved:
        return resolved[ref]
    handle = ref if ref.startswith("@") else "@" + ref
    page = get_text("https://www.youtube.com/" + urllib.parse.quote(handle, safe="@")) or ""
    m = FEED_LINK.search(page) or CANON.search(page) or re.search(r'"(?:channelId|externalId)":"(UC[A-Za-z0-9_-]{22})"', page)
    if m:
        resolved[ref] = m.group(1)
        return m.group(1)
    if page == "" and handle in KNOWN_CHANNEL_IDS:
        resolved[ref] = KNOWN_CHANNEL_IDS[handle]
        return KNOWN_CHANNEL_IDS[handle]
    if "<title>Before you continue to YouTube</title>" in page and handle in KNOWN_CHANNEL_IDS:
        resolved[ref] = KNOWN_CHANNEL_IDS[handle]
        return KNOWN_CHANNEL_IDS[handle]
    raise RuntimeError(f"could not resolve {handle} to a channel id (use the UC... id instead)")


def parse_feed(xml, per_channel=3):
    if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise ValueError("refusing XML with DTD/entities")
    root, out = ET.fromstring(xml), []
    for e in root.findall("a:entry", NS)[: per_channel * 3]:
        vid = e.findtext("yt:videoId", namespaces=NS)
        link = e.find("a:link[@rel='alternate']", NS)
        title = (e.findtext("a:title", namespaces=NS) or "").strip()
        url = link.get("href") if link is not None else (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        if not (vid and title and url) or "/shorts/" in url or re.search(r"#shorts\b", title, re.I):
            continue
        thumb = e.find("m:group/m:thumbnail", NS)
        views = e.find("m:group/m:community/m:statistics", NS)
        out.append({
            "id": vid,
            "title": title,
            "url": url,
            "channel": e.findtext("a:author/a:name", namespaces=NS) or "",
            "published": e.findtext("a:published", namespaces=NS),
            "thumbnail": thumb.get("url") if thumb is not None else f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "views": int(views.get("views")) if views is not None and (views.get("views") or "").isdigit() else None,
        })
    return out[:per_channel]


def search_api(get_json, key, query, since_iso, n=8):
    url = (
        "https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&order=date&maxResults=%d&publishedAfter=%s&q=%s&key=%s"
        % (n, urllib.parse.quote(since_iso), urllib.parse.quote(query), key)
    )
    return [
        {
            "id": i["id"]["videoId"],
            "title": html.unescape(i["snippet"]["title"]),
            "url": "https://www.youtube.com/watch?v=" + i["id"]["videoId"],
            "channel": html.unescape(i["snippet"].get("channelTitle", "")),
            "published": i["snippet"]["publishedAt"],
            "thumbnail": ((i["snippet"].get("thumbnails") or {}).get("medium") or {}).get("url") or f"https://i.ytimg.com/vi/{i['id']['videoId']}/mqdefault.jpg",
            "views": None,
        }
        for i in get_json(url).get("items", [])
        if (i.get("id") or {}).get("videoId")
    ]


def collect(cfg, get_text, get_json, resolved, key=None, now=None, redact=lambda s: s):
    """-> ({'news': [...], 'tech': [...]}, health[list], resolved). One failing channel never stops the rest."""
    now = now or dt.datetime.now(dt.timezone.utc)
    sections, health = {}, []
    for sec in ("news", "tech"):
        scfg = {**DEFAULTS[sec], **(cfg.get(sec) or {})}
        maxh = scfg["max_age_days"] * 24
        items = []
        for ref in scfg["channels"]:
            try:
                cid = resolve_channel(ref, get_text, resolved)
                got = parse_feed(get_text("https://www.youtube.com/feeds/videos.xml?channel_id=" + cid) or "<feed xmlns='http://www.w3.org/2005/Atom'/>", cfg.get("per_channel", 3))
                items += got
                health.append({"section": sec, "source": ref, "count": len(got), "error": None})
            except Exception as e:
                health.append({"section": sec, "source": ref, "count": 0, "error": redact(str(e))[:200]})
        if key:
            since = (now - dt.timedelta(days=scfg["max_age_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
            for q in scfg.get("queries", []):
                try:
                    got = search_api(get_json, key, q, since)
                    items += got
                    health.append({"section": sec, "source": f"search:{q}", "count": len(got), "error": None})
                except Exception as e:
                    health.append({"section": sec, "source": f"search:{q}", "count": 0, "error": redact(str(e))[:200]})
        seen, fresh = set(), []
        for it in sorted(items, key=lambda x: x.get("published") or "", reverse=True):
            h = age_hours(it["published"], now)
            if it["id"] in seen or h is None or h > maxh or h < -1:
                continue
            seen.add(it["id"])
            fresh.append(it)
        sections[sec] = fresh[: cfg.get("limit", 12)]
    return sections, health, resolved
