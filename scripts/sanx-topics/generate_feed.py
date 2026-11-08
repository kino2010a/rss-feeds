#!/usr/bin/env python3
"""Generate RSS (with thumbnails) for San-X official topics.
Parses the article data embedded in https://www.san-x.co.jp/ja/topics/
(pages 1..5, 12 per page). Article URL: /ja/blog/<slug>/ . Stdlib only.
"""
import urllib.request, json, os
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import xml.etree.ElementTree as ET
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE = "https://www.san-x.co.jp"
LIST_URL = BASE + "/ja/topics/"
PAGES = 5
HERE = Path(__file__).resolve().parent

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Muse feed checker)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")

def extract_articles(html):
    un = html.replace('\\"', '"')
    i = un.find('"data":[{"id":')
    if i < 0:
        return []
    start = un.find("[", i)
    depth = 0; instr = False; esc = False; end = None
    for j in range(start, len(un)):
        c = un[j]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c == "[": depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0: end = j; break
    return json.loads(un[start:end+1])

def mime_of(url):
    if url.endswith(".webp"): return "image/webp"
    if url.endswith(".png"): return "image/png"
    if url.endswith(".gif"): return "image/gif"
    return "image/jpeg"

def main():
    by_id = {}
    for p in range(1, PAGES + 1):
        url = LIST_URL if p == 1 else f"{LIST_URL}?page={p}"
        for a in extract_articles(fetch(url)):
            if a.get("status") == "public" and a.get("id") not in by_id:
                by_id[a["id"]] = a
    items = []
    for a in by_id.values():
        link = a.get("linkUrl") or f"{BASE}/ja/blog/{a['slug']}/"
        thumb = a.get("thumbnailImageUrl") or a.get("ogImageUrl") or ""
        if thumb and thumb.startswith("/"): thumb = BASE + thumb
        dt = datetime.fromtimestamp(a["publishedAt"] / 1000, JST)
        items.append({"id": a["id"], "title": a.get("pageTitle", ""), "date": dt,
                      "url": link, "thumb": thumb})
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:30]  # cap: latest 30 items only (pit, 2026-11-03)
    # Repo/Actions mode (FEED_OUT set): if the published feed already has the
    # same items in the same order, skip rewriting so no empty commit is made.
    feed_out = Path(os.environ.get("FEED_OUT", HERE / "feed.xml"))
    if "FEED_OUT" in os.environ and os.environ.get("FORCE_WRITE") != "1" and feed_out.exists():
        try:
            old_root = ET.parse(feed_out).getroot()
            old_links = [it.findtext("link") for it in old_root.find("channel").findall("item")]
            if old_links == [it["url"] for it in items]:
                print("no change: published feed already up to date")
                return
        except Exception:
            pass
    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    now = datetime.now(JST)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
             "<channel>",
             "<title>最新トピック | サンエックス</title>",
             f"<link>{LIST_URL}</link>",
             "<description>サンエックス公式サイトのトピックス（非公式フィード）。サムネイル付き。</description>",
             "<language>ja</language>",
             f"<lastBuildDate>{format_datetime(now)}</lastBuildDate>"]
    for it in items:
        desc_html = ""
        if it["thumb"]:
            desc_html = f'<img src="{it["thumb"]}" alt="" /><br />'
        desc_html += f'{esc(it["title"])}（サンエックス トピックス）'
        lines += ["<item>", f"<title>{esc(it['title'])}</title>", f"<link>{esc(it['url'])}</link>",
                  f'<guid isPermaLink="true">{esc(it["url"])}</guid>',
                  f"<pubDate>{format_datetime(it['date'])}</pubDate>"]
        if it["thumb"]:
            lines.append(f'<enclosure url="{esc(it["thumb"])}" type="{mime_of(it["thumb"])}" length="0" />')
            lines.append(f'<media:thumbnail url="{esc(it["thumb"])}" />')
            lines.append(f'<media:content url="{esc(it["thumb"])}" medium="image" type="{mime_of(it["thumb"])}" />')
        lines.append(f"<description>{esc(it['title'])}（サンエックス トピックス）</description>")
        lines.append(f"<content:encoded><![CDATA[{desc_html}]]></content:encoded>")
        lines.append("</item>")
    lines.append("</channel></rss>")
    xml = "\n".join(lines) + "\n"
    ET.fromstring(xml)
    feed_out.write_text(xml, encoding="utf-8")
    state = {"source": LIST_URL, "item_count": len(items),
             "article_ids": [it["id"] for it in items],
             "latest": {"title": items[0]["title"], "date": items[0]["date"].date().isoformat(),
                        "url": items[0]["url"]},
             "generated_at_jst": now.isoformat()}
    if os.environ.get("NO_STATE") != "1":
        (HERE / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2)[:600])

if __name__ == "__main__":
    main()
