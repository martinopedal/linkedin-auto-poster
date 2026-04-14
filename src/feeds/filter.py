"""Filter and score news items by topic relevance."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from src.feeds.fetcher import NewsItem

logger = logging.getLogger(__name__)

# Weights for update type classification
UPDATE_TYPE_WEIGHTS = {
    "ga": 3,
    "general availability": 3,
    "generally available": 3,
    "launched": 3,
    "preview": 2,
    "public preview": 2,
    "private preview": 1,
    "notice": 1,
    "blog": 1,
    "retirement": 2,
    "deprecated": 2,
}

# High-relevance keywords for preview standalone override.
# A public preview matching one strong keyword gets routed to standalone.
HIGH_RELEVANCE_PREVIEW_KEYWORDS = [
    "AKS", "Kubernetes", "Karpenter",
    "Landing Zone", "Enterprise-Scale", "CAF",
    "Terraform", "Bicep",
    "AI Foundry", "Foundry", "Copilot",
    "private endpoint", "DNS", "firewall",
    "Defender for Cloud", "zero trust",
    "sovereign", "Azure Local", "Arc",
]


def _classify_update_type(item: NewsItem) -> int:
    """Determine the update type weight from title, summary, and categories."""
    text = f"{item.title} {item.summary} {' '.join(item.categories)}".lower()
    best_weight = 0
    for keyword, weight in UPDATE_TYPE_WEIGHTS.items():
        if keyword in text:
            best_weight = max(best_weight, weight)
    return best_weight if best_weight > 0 else 1


def _count_keyword_matches(text: str, keywords: list[str]) -> int:
    """Count how many keywords appear in the text (case-insensitive)."""
    text_lower = text.lower()
    count = 0
    for kw in keywords:
        pattern = re.compile(r"\b" + re.escape(kw.lower()) + r"\b", re.IGNORECASE)
        if pattern.search(text_lower):
            count += 1
    return count


def _has_exclude_match(text: str, exclude_keywords: list[str]) -> bool:
    """Check if any exclude keyword appears in the text."""
    text_lower = text.lower()
    for kw in exclude_keywords:
        pattern = re.compile(r"\b" + re.escape(kw.lower()) + r"\b", re.IGNORECASE)
        if pattern.search(text_lower):
            return True
    return False


def score_item(
    item: NewsItem,
    include_keywords: list[str],
    exclude_keywords: list[str],
) -> int:
    """Score a news item. Returns 0 if it should be excluded."""
    searchable = f"{item.title} {item.summary} {' '.join(item.categories)}"

    if _has_exclude_match(searchable, exclude_keywords):
        logger.debug("Excluded (keyword match): %s", item.title)
        return 0

    include_hits = _count_keyword_matches(searchable, include_keywords)
    if include_hits == 0:
        logger.debug("No include keyword match: %s", item.title)
        return 0

    type_weight = _classify_update_type(item)

    # Category hits count double (more reliable than free-text)
    category_text = " ".join(item.categories)
    category_hits = _count_keyword_matches(category_text, include_keywords)

    score = type_weight + include_hits + category_hits
    return score


def is_high_relevance_preview(item: NewsItem) -> bool:
    """Check if this is a public preview of a high-relevance feature.

    Returns True if the item mentions public preview (not private)
    and matches at least one high-relevance keyword.
    """
    text = f"{item.title} {item.summary}".lower()

    # Must be public preview (not private preview)
    if "private preview" in text:
        return False
    if "public preview" not in text and "in preview" not in text:
        if "preview" not in text:
            return False

    # Must match at least one high-relevance keyword
    for kw in HIGH_RELEVANCE_PREVIEW_KEYWORDS:
        pattern = re.compile(
            r"\b" + re.escape(kw.lower()) + r"\b", re.IGNORECASE
        )
        if pattern.search(text):
            logger.info(
                "High-relevance preview detected: %s (matched: %s)",
                item.title, kw,
            )
            return True

    return False


def filter_and_score(
    items: list[NewsItem],
    include_keywords: list[str],
    exclude_keywords: list[str],
    min_score: int = 3,
    max_items: int = 5,
    seen_urls: set[str] | None = None,
    seen_title_hashes: set[str] | None = None,
    dedup_window_days: int = 7,
) -> list[tuple[NewsItem, int]]:
    """Filter, deduplicate, score, and rank news items.

    Args:
        items: Raw news items from RSS feeds.
        include_keywords: Keywords that must match for inclusion.
        exclude_keywords: Keywords that trigger exclusion.
        min_score: Minimum significance score to keep.
        max_items: Maximum number of items to return.
        seen_urls: Set of previously seen normalized URLs.
        seen_title_hashes: Set of previously seen title hashes.
        dedup_window_days: Only dedup against items within this window.

    Returns:
        List of (NewsItem, score) tuples, sorted by score descending.
    """
    seen_urls = seen_urls or set()
    seen_title_hashes = seen_title_hashes or set()
    cutoff = datetime.now(UTC) - timedelta(days=dedup_window_days)

    scored: list[tuple[NewsItem, int]] = []

    for item in items:
        # Dedup against state
        if item.normalized_url in seen_urls:
            logger.debug("Already seen (URL): %s", item.title)
            continue
        if item.title_hash in seen_title_hashes:
            logger.debug("Already seen (title): %s", item.title)
            continue

        # Skip items older than dedup window
        if item.published < cutoff:
            logger.debug("Too old (outside %d-day window): %s", dedup_window_days, item.title)
            continue

        score = score_item(item, include_keywords, exclude_keywords)
        if score >= min_score:
            scored.append((item, score))
        else:
            logger.debug("Below threshold (score=%d): %s", score, item.title)

    # Sort by score descending, then by published date descending
    scored.sort(key=lambda x: (x[1], x[0].published), reverse=True)

    result = scored[:max_items]
    logger.info("Filtered to %d items (from %d total, min_score=%d)", len(result), len(items), min_score)
    return result
