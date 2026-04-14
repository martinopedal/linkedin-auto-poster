"""Tests for news filter and scorer."""

from datetime import UTC, datetime, timedelta

from src.feeds.fetcher import NewsItem
from src.feeds.filter import filter_and_score, score_item

INCLUDE = ["Kubernetes", "AKS", "database", "Cosmos DB", "infrastructure", "Foundry", "AI"]
EXCLUDE = ["Entra", "Active Directory", "Microsoft 365", "Teams", "Intune"]


def _make_item(title: str, summary: str = "", categories: list[str] | None = None, age_days: int = 0) -> NewsItem:
    return NewsItem(
        title=title,
        summary=summary or title,
        link=f"https://example.com/{title.lower().replace(' ', '-')}",
        published=datetime.now(UTC) - timedelta(days=age_days),
        categories=categories or [],
    )


class TestScoreItem:
    def test_include_match_scores_positive(self):
        item = _make_item("AKS now supports Karpenter", categories=["Kubernetes"])
        score = score_item(item, INCLUDE, EXCLUDE)
        assert score >= 3

    def test_exclude_match_scores_zero(self):
        item = _make_item("Entra ID conditional access policies updated")
        score = score_item(item, INCLUDE, EXCLUDE)
        assert score == 0

    def test_no_match_scores_zero(self):
        item = _make_item("Power BI desktop updated with new charts")
        score = score_item(item, INCLUDE, EXCLUDE)
        assert score == 0

    def test_ga_weights_higher_than_preview(self):
        ga_item = _make_item("Cosmos DB vector search is now generally available")
        preview_item = _make_item("Cosmos DB vector search is now in public preview")
        ga_score = score_item(ga_item, INCLUDE, EXCLUDE)
        preview_score = score_item(preview_item, INCLUDE, EXCLUDE)
        assert ga_score > preview_score

    def test_multiple_keyword_hits_increase_score(self):
        single = _make_item("AKS update")
        multi = _make_item("AKS Kubernetes infrastructure database update")
        assert score_item(multi, INCLUDE, EXCLUDE) > score_item(single, INCLUDE, EXCLUDE)

    def test_category_hits_count_extra(self):
        no_cat = _make_item("AKS update", categories=[])
        with_cat = _make_item("AKS update", categories=["Kubernetes", "infrastructure"])
        assert score_item(with_cat, INCLUDE, EXCLUDE) > score_item(no_cat, INCLUDE, EXCLUDE)

    def test_exclude_overrides_include(self):
        item = _make_item("AKS and Entra ID integration for Kubernetes auth")
        score = score_item(item, INCLUDE, EXCLUDE)
        assert score == 0


class TestFilterAndScore:
    def test_respects_min_score(self):
        items = [
            _make_item("AKS Kubernetes generally available infrastructure", categories=["Kubernetes"]),
            _make_item("Minor blog post"),
        ]
        result = filter_and_score(items, INCLUDE, EXCLUDE, min_score=3)
        assert len(result) == 1
        assert result[0][0].title.startswith("AKS")

    def test_respects_max_items(self):
        items = [_make_item(f"AKS Kubernetes update {i}", categories=["Kubernetes"]) for i in range(10)]
        result = filter_and_score(items, INCLUDE, EXCLUDE, min_score=1, max_items=3)
        assert len(result) <= 3

    def test_skips_seen_urls(self):
        item = _make_item("AKS Kubernetes update", categories=["Kubernetes"])
        seen = {item.normalized_url}
        result = filter_and_score([item], INCLUDE, EXCLUDE, min_score=1, seen_urls=seen)
        assert len(result) == 0

    def test_skips_seen_title_hashes(self):
        item = _make_item("AKS Kubernetes update", categories=["Kubernetes"])
        seen_hashes = {item.title_hash}
        result = filter_and_score([item], INCLUDE, EXCLUDE, min_score=1, seen_title_hashes=seen_hashes)
        assert len(result) == 0

    def test_skips_old_items(self):
        old_item = _make_item("AKS Kubernetes update", categories=["Kubernetes"], age_days=10)
        result = filter_and_score([old_item], INCLUDE, EXCLUDE, min_score=1, dedup_window_days=7)
        assert len(result) == 0

    def test_sorted_by_score_descending(self):
        low = _make_item("AKS blog post", categories=[])
        high = _make_item(
            "AKS Kubernetes Cosmos DB AI infrastructure generally available",
            categories=["Kubernetes", "database"],
        )
        result = filter_and_score([low, high], INCLUDE, EXCLUDE, min_score=1)
        assert result[0][1] >= result[-1][1]
