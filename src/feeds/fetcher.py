"""Fetch and normalize RSS feed entries."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import feedparser
import requests
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """A normalized news item from an RSS feed."""

    title: str
    summary: str
    link: str
    published: datetime
    categories: list[str] = field(default_factory=list)
    source_feed: str = ""
    normalized_url: str = ""
    title_hash: str = ""

    def __post_init__(self):
        if not self.normalized_url:
            self.normalized_url = normalize_url(self.link)
        if not self.title_hash:
            self.title_hash = hash_title(self.title)


def normalize_url(url: str) -> str:
    """Normalize a URL by stripping tracking params, lowering scheme/host."""
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "msockid", "ocid", "wt.mc_id", "WT.mc_id",
    }
    parsed = urlparse(url.strip())
    params = parse_qs(parsed.query)
    cleaned = {k: v for k, v in params.items() if k.lower() not in {p.lower() for p in tracking_params}}
    clean_query = urlencode(cleaned, doseq=True) if cleaned else ""
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        parsed.params,
        clean_query,
        "",  # drop fragment
    ))
    return normalized


def hash_title(title: str) -> str:
    """Create a normalized hash of a title for dedup comparison."""
    cleaned = re.sub(r"[^\w\s]", "", title.lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return hashlib.sha256(cleaned.encode()).hexdigest()[:16]


def parse_published_date(entry: dict) -> datetime:
    """Extract and parse the published date from a feed entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        from time import mktime
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=UTC)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        from time import mktime
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=UTC)
    return datetime.now(UTC)


def extract_categories(entry: dict) -> list[str]:
    """Extract category/tag labels from a feed entry."""
    categories = []
    if hasattr(entry, "tags"):
        for tag in entry.tags:
            if hasattr(tag, "term"):
                categories.append(tag.term)
    return categories


def _fetch_feed(url: str, timeout: int = 30) -> feedparser.FeedParserDict:
    """Fetch a feed URL with timeout and retry, returning parsed feed."""
    with requests.Session() as session:
        retries = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return feedparser.parse(resp.content)
        except requests.RequestException as e:
            logger.warning("Feed fetch failed for %s: %s", url, e)
            result = feedparser.FeedParserDict()
            result["entries"] = []
            result["bozo"] = True
            return result


def fetch_feed(url: str, feed_name: str) -> list[NewsItem]:
    """Fetch and parse a single RSS feed, returning normalized NewsItems."""
    logger.info("Fetching feed: %s (%s)", feed_name, url)
    try:
        parsed = _fetch_feed(url)
    except Exception:
        logger.exception("Failed to fetch feed: %s", url)
        return []

    if parsed.bozo and not parsed.entries:
        bozo_msg = getattr(parsed, "bozo_exception", "unknown error")
        logger.warning("Feed returned errors and no entries: %s (%s)", feed_name, bozo_msg)
        return []

    items = []
    for entry in parsed.entries:
        try:
            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", "").strip()
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                logger.debug("Skipping entry with missing title or link in %s", feed_name)
                continue

            item = NewsItem(
                title=title,
                summary=summary,
                link=link,
                published=parse_published_date(entry),
                categories=extract_categories(entry),
                source_feed=feed_name,
            )
            items.append(item)
        except Exception:
            logger.exception("Skipping malformed entry in %s", feed_name)
            continue

    logger.info("Fetched %d items from %s", len(items), feed_name)
    return items


def _normalize_title_for_dedup(title: str) -> str:
    """Normalize title for fuzzy dedup."""
    t = title.lower()
    # Normalize lifecycle stage words
    t = t.replace("generally available", "ga")
    t = t.replace("public preview", "preview")
    t = t.replace("private preview", "preview")
    # Remove common filler
    for word in ["now", "new", "the", "is", "are", "for", "in", "on", "with", "and", "a", "an"]:
        t = t.replace(f" {word} ", " ")
    # Remove punctuation and extra spaces
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def fetch_all_feeds(feeds: list[dict]) -> list[NewsItem]:
    """Fetch all configured feeds and return combined, deduplicated items.

    Args:
        feeds: List of dicts with 'url' and 'name' keys.

    Returns:
        Combined list of NewsItems, deduplicated by normalized URL and title hash.
    """
    all_items = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_normalized: set[str] = set()

    for feed_cfg in feeds:
        try:
            items = fetch_feed(feed_cfg["url"], feed_cfg["name"])
        except Exception:
            logger.exception(
                "Feed %s crashed, skipping: %s",
                feed_cfg.get("name", "unknown"),
                feed_cfg.get("url", "unknown"),
            )
            continue
        for item in items:
            if item.normalized_url in seen_urls:
                logger.debug("Skipping cross-feed duplicate (URL): %s", item.title)
                continue
            if item.title_hash in seen_titles:
                logger.debug("Skipping cross-feed duplicate (title): %s", item.title)
                continue
            norm_title = _normalize_title_for_dedup(item.title)
            if norm_title in seen_normalized:
                logger.debug("Skipping fuzzy duplicate: %s", item.title)
                continue
            seen_urls.add(item.normalized_url)
            seen_titles.add(item.title_hash)
            seen_normalized.add(norm_title)
            all_items.append(item)

    logger.info("Total unique items across all feeds: %d", len(all_items))
    return all_items
