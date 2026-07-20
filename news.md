# News Sync Script — README

This script keeps a news portal's article database up to date by pulling fresh
articles from RSS feeds, scraping full article text, tagging FIFA World Cup
2026 coverage automatically, and inserting only genuinely new articles into
MongoDB.
It differs from regular news portal beacause of following reasons:

## What changed from the original version

### Bugs fixed
1. **Silent XML parsing bug**: the original used
   `root.find("channel") or root.find(".//channel")`. In `xml.etree.ElementTree`,
   an `Element` with no child tags evaluates as **falsy** even when it was
   found — so `or` could incorrectly fall through and occasionally parse the
   wrong node, or silently return nothing. This whole hand-rolled RSS/Atom
   parser has been replaced (see below), removing the bug entirely.
2. **Fragile HTML entity handling**: manual `.replace("&amp;", ...)` chains
   in `strip_html` missed many real-world entities (`&mdash;`, `&#8217;`,
   numeric entities, etc.). Replaced with `BeautifulSoup(...).get_text()` +
   `html.unescape()`, which handles all standard entities correctly.
3. **Regex-based HTML scraping** (`scrape_full_content`) only had extraction
   rules for two of the sites (Himalayan Times, Rising Nepal) and fell back to
   "grab every `<p>` tag" for everything else — which is exactly the kind of
   thing that breaks the moment a site changes its markup, or pulls in
   unrelated `<p>` tags from navigation/related-article widgets. Replaced with
   `trafilatura`, a well-maintained article-extraction library that works
   reliably across arbitrary site layouts without per-site rules.
4. **Insecure SSL bypass**: the original disabled certificate verification
   globally via `ssl._create_unverified_context()`. This is preserved
   functionally (`verify=False` in `requests`) only because some of the target
   sites had certificate issues, but this is a **security tradeoff** — if your
   deployment environment allows it, remove `verify=False` and let requests
   validate certificates normally.

### Note on the source list
The prompt describes "3 reputed news agencies popular in Nepal," but the feed
list mixes in BBC/ESPN/Goal.com/Fox Sports alongside The Rising Nepal and The
Himalayan Times. These were kept as **supplementary World Cup 2026 sources**
(Nepali outlets rarely publish deep match-by-match World Cup coverage), but
they are clearly separated and commented in `RSS_URLS` so you can easily strip
them out if you want a purely Nepali-source feed. The Fox Sports endpoint also
depends on a `partnerKey` query parameter that may be expired — verify it
still returns data before relying on it in production.

### Libraries introduced (and why)
| Library | Replaces | Why |
|---|---|---|
| `feedparser` | ~120 lines of custom RSS 2.0 / Atom XML parsing + date-format guessing | Handles CDATA, Atom vs RSS 2.0 differences, and inconsistent date formats automatically and correctly. |
| `requests` | `urllib.request` + manual header/SSL boilerplate | Simpler, more robust HTTP client with automatic status-code error handling. |
| `trafilatura` | Site-specific regex scrapers + generic `<p>`-tag fallback | Purpose-built, actively maintained library for extracting the main body text of a news article from raw HTML, regardless of site layout. |
| `beautifulsoup4` | Regex-based tag stripping and `og:image` lookup | Proper HTML parsing instead of regex-on-HTML, which is inherently fragile (nested tags, malformed markup, etc.). |

Net effect: the same behavior, but far less custom parsing code to maintain,
and article-text/image extraction that will keep working even if a source
site changes its HTML structure.

### Install requirements
```bash
pip install requests feedparser beautifulsoup4 trafilatura
```

## How the script works

1. **`RSS_URLS`** — the list of RSS/Atom feed endpoints to pull from.
2. **`collect_latest_items(limit=40)`**
   - Fetches each feed URL with `requests`.
   - Parses it with `feedparser` (works for both RSS 2.0 and Atom feeds).
   - Cleans titles/descriptions with `strip_html`.
   - Deduplicates by exact URL and by **title similarity** (word-overlap
     Jaccard score ≥ 0.72) so the same story from two feeds isn't counted
     twice.
   - Sorts everything newest-first by published date and returns up to
     `limit` items.
3. **`is_world_cup(title, content)`** — keyword/pattern matching to detect
   FIFA World Cup 2026 coverage so it can be force-categorized regardless of
   what the general classifier would say.
4. **`scrape_full_content(url)`** — fetches the article's HTML page and uses
   `trafilatura` to pull out the clean article body text, plus a featured
   image URL (from article metadata, falling back to the page's
   `og:image`/`twitter:image` meta tag).
5. **`guess_source(link)`** — maps a URL's domain to a `(source_id,
   source_name)` pair for display purposes.
6. **`run_sync(db, ARTICLES_CACHE, categorize_fn, summarize_fn, utc_iso_fn, sync_db_fn)`**
   — the entry point your app calls. It:
   - Collects candidate items.
   - Filters out anything already in the in-memory cache or MongoDB
     (by URL and by title similarity).
   - Scrapes full content for each new candidate (falling back to the RSS
     description if scraping comes back too short).
   - Categorizes each article — automatically as `"World Cup 2026"` if
     detected, otherwise via your supplied `categorize_fn`.
   - Summarizes it via your supplied `summarize_fn`.
   - Inserts the new article document into MongoDB and the in-memory cache.
   - Calls your supplied `sync_db_fn("articles")` once at the end.
   - Returns the count of newly added articles.

### Function parameters you must supply
`run_sync` is deliberately dependency-injected so this file stays
self-contained and testable:
- `db` — a MongoDB client/database object exposing `db.articles`.
- `ARTICLES_CACHE` — a mutable Python list acting as your in-memory article cache.
- `categorize_fn(text) -> str` — your existing category classifier.
- `summarize_fn(text, num_sentences) -> str` — your existing summarizer.
- `utc_iso_fn() -> str` — a function returning the current UTC time as an ISO string.
- `sync_db_fn(collection_name)` — your existing function to persist/flush the DB.

## Known limitations / things to watch
- `verify=False` disables TLS certificate checks for all requests — a
  deliberate tradeoff kept from the original code to work around some sites'
  certificate issues. Remove it if your target sites support proper HTTPS.
- The Fox Sports feed URL embeds a `partnerKey` that may expire; monitor logs
  for repeated failures on that specific feed.
- Title-similarity dedup is a simple word-overlap heuristic — it will not
  catch every rephrased duplicate, and can very rarely flag two genuinely
  different but similarly-worded headlines as duplicates. Adjust the
  `threshold` in `_titles_are_similar` if you see false positives/negatives.
