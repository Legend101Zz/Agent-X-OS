"""Free-tier public-source providers for the F1/F4/F5 mandate-discovery adapters.

When ``FIRECRAWL_API_KEY`` is not configured (or has expired), the
discovery_adapters fall back to these providers so the mandate can
still produce a meaningful portfolio. The providers use public,
unauthenticated endpoints:

  - HN Algolia search (no auth): ``https://hn.algolia.com/api/v1/search``
  - Reddit JSON (no auth, but reddit.com may rate-limit):
    ``https://www.reddit.com/r/<sub>/new.json?limit=N``
  - Product Hunt via RSS (no auth): ``https://www.producthunt.com/feed``

This is **explicitly a Phase 14 stopgap**: the principled fix is a
working Firecrawl key, but the free-tier path is a valid
``ad-hoc_execution`` per the GREEN / AMBER / RED mandate-rung
classification — the run produces a portfolio, just from a
narrower source set.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"
REDDIT_JSON_URL = "https://www.reddit.com/r/{subreddit}/new.json"
PRODUCTHUNT_RSS_URL = "https://www.producthunt.com/feed"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Agent-X-OS/1.0 (mandate-discovery; +https://github.com/Legend101Zz/Agent-X-OS)"  # noqa: E501

# Recency window: posts older than this are filtered out (the F1
# charter rule: < 12 months unless structural_shift=true).
F1_DEFAULT_RECENCY_MONTHS = 12


def _http_get_json(url: str, *, timeout: int = 30) -> Any:
    """GET a JSON URL with a sane user agent. Returns parsed JSON or raises."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, *, timeout: int = 30) -> str:
    """GET a text URL (RSS feed)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return str(resp.read().decode("utf-8", errors="replace"))


def search_hackernews(segment: str, *, limit: int = 30) -> list[dict[str, Any]]:
    """Search HN via Algolia for stories AND comments matching ``segment``.

    Comments are usually the source of the real pain signal (founders
    asking for help, complaining about workflow); stories are the
    Show HN / Ask HN context. We pull both.
    """
    out: list[dict[str, Any]] = []
    for tag_filter in ("story", "comment"):
        query = segment.strip()
        url = f"{HN_ALGOLIA_URL}?query={urllib.parse.quote(query)}&tags={tag_filter}&hitsPerPage={limit}"
        try:
            data = _http_get_json(url)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            out.append(
                {
                    "source": "hackernews",
                    "url": "",
                    "title": "",
                    "author": "",
                    "timestamp": "",
                    "upvotes": 0,
                    "body_text": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        hits = data.get("hits", []) if isinstance(data, dict) else []
        for h in hits:
            title = h.get("story_title") or h.get("title") or ""
            text = h.get("story_text") or h.get("comment_text") or ""
            # Strip HTML — Algolia serves the raw HTML
            cleaned = re.sub(r"<[^>]+>", " ", text).strip()
            if not cleaned and not title:
                continue
            body = f"{title}. {cleaned}"[:600].strip() if cleaned else title
            if tag_filter == "story":
                url_value = f"https://news.ycombinator.com/item?id={h.get('objectID', '')}"
            else:
                # Comment: objectID is the comment id, parent_id is the story
                parent = h.get("story_id") or h.get("parent_id") or h.get("objectID", "")
                url_value = f"https://news.ycombinator.com/item?id={parent}"
            out.append(
                {
                    "url": url_value,
                    "author": h.get("author", ""),
                    "timestamp": h.get("created_at", ""),
                    "upvotes": int(h.get("points") or 0),
                    "body_text": body,
                    "title": title,
                    "source": "hackernews",
                }
            )
    return out


def search_reddit(segment: str, *, limit: int = 30) -> list[dict[str, Any]]:
    """Sample 1-2 subreddit new-feeds filtered to ``segment`` keywords."""
    subreddits = _subreddits_for_segment(segment)
    if not subreddits:
        return []
    out: list[dict[str, Any]] = []
    for sub in subreddits[:2]:  # rate-limit: 2 subreddits per call
        url = REDDIT_JSON_URL.format(subreddit=sub) + f"?limit={min(limit, 25)}"
        try:
            data = _http_get_json(url)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            out.append(
                {
                    "source": "reddit",
                    "url": f"https://reddit.com/r/{sub}",
                    "title": "",
                    "author": "",
                    "timestamp": "",
                    "upvotes": 0,
                    "body_text": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        children = data.get("data", {}).get("children", []) if isinstance(data, dict) else []
        for c in children:
            d = c.get("data", {}) if isinstance(c, dict) else {}
            selftext = d.get("selftext") or ""
            if not selftext.strip():
                # skip link/image-only posts; F2 needs body_text
                continue
            ts_value = d.get("created_utc")
            timestamp = ""
            if isinstance(ts_value, (int, float)) and ts_value > 0:
                timestamp = datetime.fromtimestamp(ts_value, tz=UTC).isoformat()
            out.append(
                {
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "author": d.get("author", ""),
                    "timestamp": timestamp,
                    "upvotes": int(d.get("score") or 0),
                    "body_text": selftext[:600],
                    "title": d.get("title", ""),
                    "source": "reddit",
                }
            )
    return out


def search_producthunt(segment: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Pull the latest posts from Product Hunt's RSS feed and filter by segment keyword."""
    try:
        body = _http_get_text(PRODUCTHUNT_RSS_URL)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [
            {
                "source": "producthunt",
                "url": "",
                "title": "",
                "author": "",
                "timestamp": "",
                "upvotes": 0,
                "body_text": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
        ]
    items = re.findall(r"<entry>(.*?)</entry>", body, re.DOTALL)
    keywords = [
        w.lower()
        for w in re.findall(r"\w{4,}", segment)
        if w.lower() not in _STOPWORDS_FOR_PH
    ]
    out: list[dict[str, Any]] = []
    for raw_item in items[: limit * 3]:
        title_m = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", raw_item, re.DOTALL)
        link_m = re.search(r"<link[^>]+rel=\"alternate\"[^>]+href=\"([^\"]+)\"", raw_item)
        if not link_m:
            # Fall back to rel="alternate" with href first
            link_m = re.search(r"rel=\"alternate\"[^>]+href=\"([^\"]+)\"", raw_item)
        pub_m = re.search(r"<published>(.*?)</published>", raw_item)
        desc_m = re.search(r"<content[^>]*>(.*?)</content>", raw_item, re.DOTALL)
        title = (title_m.group(1) if title_m else "").strip()
        link = (link_m.group(1) if link_m else "").strip()
        pub = (pub_m.group(1) if pub_m else "").strip()
        desc = re.sub(r"<[^>]+>", " ", (desc_m.group(1) if desc_m else "")).strip()[:1500]
        if not (title and link):
            continue
        if keywords and not any(k in (title + " " + desc).lower() for k in keywords):
            continue
        out.append(
            {
                "url": link,
                "author": "producthunt",
                "timestamp": pub,
                "upvotes": 0,
                "body_text": desc or title,
                "title": title,
                "source": "producthunt",
            }
        )
        if len(out) >= limit:
            break
    return out


def _subreddits_for_segment(segment: str) -> tuple[str, ...]:
    """Pick 1-2 subreddits based on segment keywords."""
    seg_lower = segment.lower()
    matched: list[str] = []
    for keyword, subs in _SEGMENT_SUBREDDITS.items():
        if keyword in seg_lower:
            matched.extend(subs)
    seen: set[str] = set()
    out: list[str] = []
    for s in matched:
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= 2:
            break
    if not out:
        out = ["Entrepreneur", "startups"]
    return tuple(out)


# Subreddit allowlist per segment keyword. The keys are loose segment
# matches; values are the subreddits most likely to contain the
# relevant pain. Deliberately a small curated list (not the full
# Top 5000) — we want quality, not volume.
_SEGMENT_SUBREDDITS: dict[str, tuple[str, ...]] = {
    "revops": ("RevOps", "SalesOperations", "sales"),
    "saas": ("SaaS", "startups", "Entrepreneur"),
    "crm": ("sales", "SalesOperations", "HubSpot", "Salesforce"),
    "lead": ("sales", "B2BSales", "SalesOperations", "coldemail"),
    "founder": ("Entrepreneur", "startups", "smallbusiness"),
    "agency": ("agency", "freelance", "consulting"),
    "consulting": ("consulting", "agency", "freelance"),
    "sdr": ("sales", "B2BSales", "SalesOperations"),
    "ae": ("sales", "B2BSales"),
    "operations": ("RevOps", "SalesOperations", "Entrepreneur"),
    "marketing": ("marketing", "B2BMarketing", "growth"),
    "indie": ("IndieHackers", "Entrepreneur", "startups"),
    "consultant": ("consulting", "agency"),
    "customer": ("CustomerSuccess", "CustomerService", "Entrepreneur"),
    "support": ("CustomerService", "CustomerSuccess"),
    "data": ("dataengineering", "dataengineering", "MachineLearning"),
    "engineer": ("ExperiencedDevs", "ExperiencedDevs", "sysadmin"),
    "developer": ("ExperiencedDevs", "ExperiencedDevs", "webdev"),
    "recruit": ("recruiting", "HumanResources", "Jobs"),
    "hr": ("HumanResources", "Jobs"),
    "finance": ("Accounting", "Finance", "smallbusiness"),
    "legal": ("LegalAdvice", "smallbusiness", "Entrepreneur"),
}


_STOPWORDS_FOR_PH = frozenset({"the", "and", "for", "with", "this", "that", "from"})
