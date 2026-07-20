import re
import html
from datetime import datetime
from urllib.parse import urlparse

import requests # type: ignore
import feedparser # type: ignore
import trafilatura # type: ignore
from bs4 import BeautifulSoup # type: ignore
import urllib3 # type: ignore

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REQUEST_TIMEOUT = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, "
              "text/xml;q=0.8, */*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}

RSS_URLS = [
    "https://risingnepaldaily.com/rss",
    "https://thehimalayantimes.com/feed",       # Main feed 
    "https://thehimalayantimes.com/rssFeed/19", # Education
    "https://thehimalayantimes.com/rssFeed/11", # Business
    "https://thehimalayantimes.com/rssFeed/31", # Environment
    "https://thehimalayantimes.com/rssFeed/16", # Entertainment
    "https://thehimalayantimes.com/rssFeed/15", # Nepal
    "https://thehimalayantimes.com/rssFeed/5",  # International
    "https://thehimalayantimes.com/rssFeed/17", # Science and Tech
    "https://thehimalayantimes.com/rssFeed/13", # Sports
    "https://feeds.bbci.co.uk/sport/football/world-cup/rss.xml",  # BBC World Cup
    "https://feeds.bbci.co.uk/sport/football/rss.xml",            # BBC Football
    "https://feeds.bbci.co.uk/sport/rss.xml",                     # BBC Sport (all)

]

_WC_PATTERNS = [
    "world cup 2026", "2026 world cup", "fifa 2026", "2026 fifa",
    "fifa world cup 2026", "world cup final", "world cup semifinal",
    "world cup quarter", "world cup group stage", "wc2026", "worldcup2026",
    "world cup match", "world cup goal", "world cup winner",
    "world cup host", "world cup draw", "world cup squad",
    "usa 2026", "canada 2026", "mexico 2026", "north america 2026",
    "world cup qualifier", "world cup standings",
]


def is_world_cup(title, content):
    text = ((title or "") + " " + (content or "")).lower()
    if any(p in text for p in _WC_PATTERNS):
        return True
    if "world cup" in text and "2026" in text:
        return True
    if "fifa" in text and ("2026" in text or "world cup" in text):
        return True
    return False

def fetch_url(url, timeout=REQUEST_TIMEOUT):
    print(f"Fetching: {url}...", end=" ", flush=True)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
        resp.raise_for_status()
        print(f"OK ({len(resp.content)} bytes)")
        return resp.content
    except Exception as e:
        print(f"FAILED: {e}")
        return None

def strip_html(text):
    if not text:
        return ""
    clean = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", html.unescape(clean)).strip()

_SOURCE_DOMAIN_MAP = {
    "risingnepaldaily.com": ("therisingnepal", "The Rising Nepal"),
    "thehimalayantimes.com": ("the-himalayan-times", "The Himalayan Times"),
    "bbci.co.uk": ("bbc-sport", "BBC Sport"),
    "bbc.com": ("bbc-sport", "BBC Sport"),
}

def guess_source(link):
    netloc = urlparse(link).netloc.lower()
    for domain, value in _SOURCE_DOMAIN_MAP.items():
        if domain in netloc:
            return value
    return "external", "BBC Sports"

def _normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()

def _titles_are_similar(t1, t2, threshold=0.72):
    words1 = set(_normalize_title(t1).split())
    words2 = set(_normalize_title(t2).split())
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2)
    return (overlap / max(len(words1), len(words2))) >= threshold

def scrape_full_content(url):
    html_bytes = fetch_url(url)
    if not html_bytes:
        return "", None

    html_text = html_bytes.decode("utf-8", "ignore")

    full_text = trafilatura.extract(
        html_text,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    ) or ""

    image_url = None
    try:
        meta = trafilatura.extract_metadata(html_text, default_url=url)
        if meta and meta.image:
            image_url = meta.image
    except Exception:
        pass

    if not image_url:
        soup = BeautifulSoup(html_text, "html.parser")
        tag = (soup.find("meta", property="og:image")
               or soup.find("meta", attrs={"name": "twitter:image"}))
        if tag and tag.get("content"):
            image_url = tag["content"].strip()

    return full_text.strip(), image_url

def collect_latest_items(limit=40):
    all_items = []
    seen_links = set()
    seen_titles = []

    for url in RSS_URLS:
        raw = fetch_url(url)
        if not raw:
            continue

        feed = feedparser.parse(raw)
        print(f"  → Parsed {len(feed.entries)} items from {url}")

        for entry in feed.entries:
            title = strip_html(entry.get("title", ""))
            link = (entry.get("link") or "").strip()
            desc = strip_html(entry.get("summary", "") or entry.get("description", ""))

            pub_dt = None
            if entry.get("published_parsed"):
                pub_dt = datetime(*entry.published_parsed[:6])
            elif entry.get("updated_parsed"):
                pub_dt = datetime(*entry.updated_parsed[:6])

            if not title or not link:
                continue
            if link in seen_links:
                continue
            if any(_titles_are_similar(title, t) for t in seen_titles):
                print(f"    [Dup title] {title[:55]}")
                continue

            seen_links.add(link)
            seen_titles.append(title)
            all_items.append({
                "title": title,
                "link": link,
                "description": desc,
                "pub_dt": pub_dt,
            })

    all_items.sort(key=lambda it: it["pub_dt"] or datetime.min, reverse=True)
    return all_items[:limit]

def run_sync(db, ARTICLES_CACHE, categorize_fn, summarize_fn, utc_iso_fn, sync_db_fn):
    
    print("=" * 60)
    print("Starting news sync (up to 40 articles)...")
    print("=" * 60)
    items = collect_latest_items(40)
    print(f"RSS collection yielded {len(items)} unique candidate items.")

    existing_urls = set()
    for a in ARTICLES_CACHE:
        u = a.get("url") or ""
        if u:
            existing_urls.add(u)
    for doc in db.articles.find({}, {"url": 1}):
        u = doc.get("url") or ""
        if u:
            existing_urls.add(u)

    existing_titles = [a.get("title", "") for a in ARTICLES_CACHE if a.get("title")]

    max_id = 0
    for a in ARTICLES_CACHE:
        try:
            max_id = max(max_id, int(a.get("article_id", 0)))
        except (ValueError, TypeError):
            pass
    for doc in db.articles.find({}, {"article_id": 1}):
        try:
            max_id = max(max_id, int(doc.get("article_id", 0)))
        except (ValueError, TypeError):
            pass

    new_count = 0
    for item in items:
        link = item.get("link") or ""
        title = item.get("title") or ""

        if not link:
            continue

        if link in existing_urls:
            print(f"  [Skip-URL] {title[:55]}")
            continue

        if any(_titles_are_similar(title, et) for et in existing_titles):
            print(f"  [Skip-Title] {title[:55]}")
            continue

        print(f"\n  → Scraping: {title[:55]}")
        article_content, article_image = scrape_full_content(link)

        if not article_content or len(article_content) < 100:
            rss_desc = item.get("description", "")
            if rss_desc and len(rss_desc) > len(article_content or ""):
                article_content = rss_desc
                print("    [Using RSS description fallback]")

        if not article_content:
            print("    [Skipped — no content]")
            continue

        categorize_input = title + " " + article_content
        if is_world_cup(title, article_content):
            category = "World Cup 2026"
            print("    [Category] World Cup 2026 (auto-detected)")
        else:
            category = categorize_fn(categorize_input)
            print(f"    [Category] {category}")

        summary = summarize_fn(article_content, 3)
        source_id, source_name = guess_source(link)

        max_id += 1
        new_post = {
            "article_id": str(max_id),
            "title": title,
            "category": category,
            "description": summary,
            "summary": summary,
            "full_content": article_content,
            "url": link,
            "url_to_image": article_image,
            "source_id": source_id,
            "source_name": source_name,
            "published_at": utc_iso_fn(),
            "synced": True,
        }

        db.articles.insert_one(new_post)
        new_count += 1
        ARTICLES_CACHE.insert(0, new_post)
        existing_urls.add(link)
        existing_titles.append(title)
        print(f"    [Added #{max_id}] {title[:55]}")

    sync_db_fn("articles")
    print("=" * 60)
    print(f"Sync complete: +{new_count} new article(s).")
    print("=" * 60)
    return new_count


if __name__ == "__main__":
    pass