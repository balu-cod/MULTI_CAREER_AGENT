import datetime as dt, tempfile, unittest
from unittest import mock
from live import runtime, youtube as Y
from live.tools import redact
from live.vault import VaultAgent

NOW = dt.datetime.now(dt.timezone.utc)
def ago(h): return (NOW - dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

def feed(*entries):
    body = "".join(f"""<entry><yt:videoId>{i}</yt:videoId><title>{t}</title><link rel="alternate" href="{u}"/><author><name>{c}</name></author><published>{p}</published>
      <media:group><media:thumbnail url="https://i.ytimg.com/vi/{i}/hqdefault.jpg"/><media:community><media:statistics views="{v}"/></media:community></media:group></entry>""" for i, t, u, c, p, v in entries)
    return f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/">{body}</feed>'

UC1, UC2 = "UC" + "a" * 22, "UC" + "b" * 22
PAGES = {
    "feeds/videos.xml?channel_id=" + UC1: feed(("v1", "New agent framework &amp; MCP", "https://www.youtube.com/watch?v=v1", "Fireship", ago(5), 1200),
                                               ("v2", "Old video", "https://www.youtube.com/watch?v=v2", "Fireship", ago(24 * 30), 5),
                                               ("v3", "Quick tip #shorts", "https://www.youtube.com/watch?v=v3", "Fireship", ago(1), 1),
                                               ("v4", "Short clip", "https://www.youtube.com/shorts/v4", "Fireship", ago(1), 1),
                                               ("v6", "From the future", "https://www.youtube.com/watch?v=v6", "Fireship", ago(-48), 1)),
    "feeds/videos.xml?channel_id=" + UC2: feed(("v5", "FastAPI deep dive", "https://www.youtube.com/watch?v=v5", "Dev Channel", ago(30), 99000)),
    "/@Fireship": f'<link rel="alternate" type="application/rss+xml" href="https://www.youtube.com/feeds/videos.xml?channel_id={UC1}">',
}
def get_text(url):
    if "/@Missing" in url: return "<html>nothing</html>"
    for k, v in PAGES.items():
        if k in url: return v
    return None


class YouTubeTests(unittest.TestCase):
    def collect(self, cfg, **kw): return Y.collect(cfg, get_text, kw.pop("get_json", lambda u: {}), kw.pop("resolved", {}), now=NOW, **kw)

    def test_news_and_tech_sections_fresh_only(self):
        cfg = {"news": {"channels": ["@Fireship"], "max_age_days": 4}, "tech": {"channels": [UC2], "max_age_days": 14}}
        secs, health, resolved = self.collect(cfg)
        self.assertEqual([v["id"] for v in secs["news"]], ["v1"])            # stale, #shorts, /shorts/ and future-dated all dropped
        self.assertEqual([v["id"] for v in secs["tech"]], ["v5"])
        v = secs["news"][0]; self.assertEqual(v["title"], "New agent framework & MCP"); self.assertEqual(v["views"], 1200); self.assertTrue(v["thumbnail"].startswith("https://i.ytimg.com/"))
        self.assertEqual(resolved["@Fireship"], UC1)                         # handle resolved once and cached

    def test_bad_handle_is_reported_not_fatal(self):
        secs, health, _ = self.collect({"news": {"channels": ["@Missing", "@Fireship"]}, "tech": {"channels": []}})
        self.assertEqual(len(secs["news"]), 1); self.assertTrue(any(h["source"] == "@Missing" and h["error"] for h in health))

    def test_api_search_merges_and_redacts_key(self):
        api = {"items": [{"id": {"videoId": "s1"}, "snippet": {"title": "Search &amp; find", "channelTitle": "Ch", "publishedAt": ago(2), "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/s1/mq.jpg"}}}}]}
        secs, _, _ = self.collect({"news": {"channels": [], "queries": ["ai news"]}, "tech": {"channels": []}}, get_json=lambda u: api, key="SECRET123")
        self.assertEqual(secs["news"][0]["title"], "Search & find")
        def boom(u): raise RuntimeError("403 for url: https://www.googleapis.com/youtube/v3/search?q=x&key=SECRET123")
        _, health, _ = self.collect({"news": {"channels": [], "queries": ["q"]}, "tech": {"channels": []}}, get_json=boom, key="SECRET123", redact=redact)
        self.assertNotIn("SECRET123", str(health))

    def test_rejects_xml_entities(self):
        with self.assertRaises(ValueError): Y.parse_feed('<!DOCTYPE x [<!ENTITY a "b">]><feed/>')

    def test_agent_saves_to_vault_and_keeps_old_data_on_total_outage(self):
        d = tempfile.mkdtemp(); v = VaultAgent(vault_dir=d, audit_path=d + "/a.log"); v.bootstrap_defaults_if_empty(); runtime.discover()
        prof = {"youtube": {"news": {"channels": ["@Fireship"]}, "tech": {"channels": [UC2]}}}
        ctx = {"vault": v, "profile": prof, "log": lambda m: None, "insights": {}}
        with mock.patch.dict(runtime.TOOLS, {"get_text": get_text, "get_json": lambda u: {}}):
            runtime.AGENTS["youtube"]().run(ctx)
        saved = v.load_artifact("youtube_updates_v1.json"); self.assertEqual(len(saved["news"]), 1); self.assertTrue(ctx["insights"]["youtube"]["tech"])
        def dead(url): raise RuntimeError("network down")
        ctx2 = {"vault": v, "profile": prof, "log": lambda m: None, "insights": {}}
        with mock.patch.dict(runtime.TOOLS, {"get_text": dead, "get_json": dead}): runtime.AGENTS["youtube"]().run(ctx2)
        self.assertEqual(len(v.load_artifact("youtube_updates_v1.json")["news"]), 1)      # outage did not blank yesterday's results

    def test_digest_includes_video_sections_escaped(self):
        from live.mailer import render_digest
        r = {"updated": "2026-11-01T08:00:00", "scanned": 0, "jobs": []}
        I = {"youtube": {"news": [{"title": "<b>x</b>", "channel": "C&D", "url": "https://www.youtube.com/watch?v=1"}], "tech": [], "health": [{"source": "@Bad", "error": "unresolved"}]}}
        text, body = render_digest(r, I); self.assertIn("NEWS VIDEOS", text); self.assertIn("&lt;b&gt;x", body); self.assertIn("youtube:@Bad", text)
