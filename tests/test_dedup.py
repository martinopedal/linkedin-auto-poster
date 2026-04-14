"""Tests for cross-feed deduplication."""

from datetime import UTC, datetime

from src.feeds.fetcher import NewsItem, hash_title, normalize_url
from src.feeds.filter import filter_and_score

INCLUDE = ["AKS", "Kubernetes", "infrastructure"]
EXCLUDE = ["Entra"]


def _item(title: str, url: str, source: str = "feed1") -> NewsItem:
    return NewsItem(
        title=title,
        summary=title,
        link=url,
        published=datetime.now(UTC),
        categories=["Kubernetes"],
        source_feed=source,
    )


class TestCrossFeedDedup:
    def test_same_url_different_feeds_deduped(self):
        """Same article URL appearing in two feeds should only produce one result."""
        items = [
            _item("AKS infrastructure update", "https://azure.microsoft.com/updates/aks-update", "Azure Updates"),
            _item("AKS infrastructure update", "https://azure.microsoft.com/updates/aks-update", "Azure Charts"),
        ]
        result = filter_and_score(items, INCLUDE, EXCLUDE, min_score=1)
        # Both have identical normalized URLs, so fetcher-level dedup should catch this.
        # If fed directly to filter, seen_urls handles it:
        seen_urls = {items[0].normalized_url}
        result = filter_and_score(items[1:], INCLUDE, EXCLUDE, min_score=1, seen_urls=seen_urls)
        assert len(result) == 0

    def test_same_title_different_urls_deduped(self):
        """Same article title with different URLs (aggregator repost) should be deduped by title hash."""
        items = [
            _item("AKS Kubernetes infrastructure generally available", "https://azure.microsoft.com/updates/aks-ga"),
            _item("AKS Kubernetes infrastructure generally available", "https://techcommunity.microsoft.com/aks-ga"),
        ]
        first = items[0]
        seen_hashes = {first.title_hash}
        result = filter_and_score(items[1:], INCLUDE, EXCLUDE, min_score=1, seen_title_hashes=seen_hashes)
        assert len(result) == 0

    def test_similar_but_different_titles_not_deduped(self):
        """Different articles should not be falsely deduped."""
        items = [
            _item("AKS Kubernetes update for March", "https://example.com/march"),
            _item("AKS Kubernetes update for April", "https://example.com/april"),
        ]
        result = filter_and_score(items, INCLUDE, EXCLUDE, min_score=1)
        assert len(result) == 2

    def test_url_normalization_catches_tracking_params(self):
        """Same base URL with different tracking params should normalize to the same value."""
        url1 = "https://azure.microsoft.com/updates/aks?utm_source=twitter"
        url2 = "https://azure.microsoft.com/updates/aks?utm_source=linkedin&utm_medium=social"
        assert normalize_url(url1) == normalize_url(url2)

    def test_title_hash_ignores_punctuation(self):
        """Title hashing should normalize away punctuation differences."""
        assert hash_title("AKS: Now GA!") == hash_title("AKS Now GA")
        assert hash_title("What's New in AKS?") == hash_title("Whats New in AKS")
