"""Tests for feature lifecycle tracker."""

from pathlib import Path

from src.feeds.tracker import (
    FeatureTracker,
    detect_stage,
    normalize_feature_name,
)


class TestDetectStage:
    def test_detects_ga(self):
        assert detect_stage("AKS node autoscaling is now generally available") == "ga"

    def test_detects_ga_short(self):
        assert detect_stage("Cosmos DB vector search GA") == "ga"

    def test_detects_now_available(self):
        assert detect_stage("Azure Firewall Premium now available in all regions") == "ga"

    def test_detects_public_preview(self):
        assert detect_stage("Container Apps dynamic sessions in public preview") == "preview"

    def test_detects_preview(self):
        assert detect_stage("New AKS networking feature in preview") == "preview"

    def test_detects_private_preview(self):
        assert detect_stage("GPU node pools enter private preview") == "private_preview"

    def test_private_preview_not_misdetected_as_preview(self):
        """Regression: private preview must not match the general preview pattern."""
        assert detect_stage("Azure AI services private preview") == "private_preview"

    def test_detects_ga_lowercase(self):
        """GA detection must be case-insensitive."""
        assert detect_stage("Feature is now ga") == "ga"

    def test_detects_deprecated(self):
        assert detect_stage("Azure classic VMs will be retired on Sep 2025") == "deprecated"

    def test_detects_deprecation(self):
        assert detect_stage("AKS legacy RBAC deprecated") == "deprecated"

    def test_returns_none_for_unknown(self):
        assert detect_stage("Azure blog post about best practices") is None


class TestNormalizeFeatureName:
    def test_strips_stage_keywords(self):
        slug = normalize_feature_name("AKS node autoscaling is now generally available")
        assert "generally" not in slug
        assert "available" not in slug
        assert "aks" in slug

    def test_strips_azure_prefix(self):
        slug = normalize_feature_name("Azure Cosmos DB vector search GA")
        assert not slug.startswith("azure")
        assert "cosmos" in slug

    def test_produces_slug_format(self):
        slug = normalize_feature_name("Container Apps dynamic sessions in public preview")
        assert " " not in slug
        assert slug == slug.lower()

    def test_different_stages_same_feature_same_slug(self):
        slug_preview = normalize_feature_name("AKS Karpenter support in preview")
        slug_ga = normalize_feature_name("AKS Karpenter support generally available")
        assert slug_preview == slug_ga

    def test_strips_version_numbers(self):
        slug_v1 = normalize_feature_name("Container Apps v1.2 in preview")
        slug_v2 = normalize_feature_name("Container Apps v2.0 generally available")
        assert slug_v1 == slug_v2

    def test_strips_region_qualifiers(self):
        slug_region = normalize_feature_name("Cosmos DB (East US) in preview")
        slug_plain = normalize_feature_name("Cosmos DB in preview")
        assert slug_region == slug_plain


class TestFeatureTracker:
    def _make_tracker(self, tmp_path: Path) -> FeatureTracker:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        return FeatureTracker(data_dir)

    def test_new_feature_returns_event(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        event = tracker.track_item(
            "AKS Karpenter support in public preview",
            "https://example.com/aks-karpenter-preview",
        )
        assert event is not None
        assert event.is_new is True
        assert event.is_progression is False
        assert event.stage == "preview"
        assert event.priority_boost > 0

    def test_same_stage_twice_returns_none(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.track_item("AKS Karpenter support in preview", "https://example.com/1")
        event = tracker.track_item("AKS Karpenter support in preview", "https://example.com/2")
        assert event is None

    def test_stage_progression_detected(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.track_item("AKS Karpenter support in preview", "https://example.com/preview")
        event = tracker.track_item(
            "AKS Karpenter support is now generally available",
            "https://example.com/ga",
        )
        assert event is not None
        assert event.is_progression is True
        assert event.previous_stage == "preview"
        assert event.stage == "ga"

    def test_ga_progression_gets_highest_boost(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.track_item("AKS Karpenter support in preview", "https://example.com/preview")
        event = tracker.track_item(
            "AKS Karpenter support is now generally available",
            "https://example.com/ga",
        )
        assert event.priority_boost == 6  # ga(3) + progression(3), capped at 6

    def test_brand_new_ga_gets_high_boost(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        event = tracker.track_item(
            "Cosmos DB vector search is now generally available",
            "https://example.com/cosmos-ga",
        )
        assert event.priority_boost == 5  # ga(3) + new(2)

    def test_mark_posted(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.track_item("AKS Karpenter support in preview", "https://example.com/1")
        slug = normalize_feature_name("AKS Karpenter support in preview")
        tracker.mark_posted(slug, "preview")
        assert tracker.was_posted_at_stage(slug, "preview") is True
        assert tracker.was_posted_at_stage(slug, "ga") is False

    def test_progression_summary(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.track_item(
            "AKS Karpenter support in preview",
            "https://example.com/preview",
            published_date="2026-01-15T06:00:00+00:00",
        )
        tracker.track_item(
            "AKS Karpenter support is now generally available",
            "https://example.com/ga",
            published_date="2026-04-15T06:00:00+00:00",
        )
        slug = normalize_feature_name("AKS Karpenter support in preview")
        summary = tracker.get_progression_summary(slug)
        assert summary is not None
        assert "preview" in summary
        assert "ga" in summary
        assert "3 months" in summary

    def test_no_summary_for_single_stage(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.track_item("AKS Karpenter support in preview", "https://example.com/1")
        slug = normalize_feature_name("AKS Karpenter support in preview")
        assert tracker.get_progression_summary(slug) is None

    def test_non_stage_article_returns_none(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        event = tracker.track_item(
            "Best practices for Azure networking",
            "https://example.com/best-practices",
        )
        assert event is None

    def test_backward_stage_ignored(self, tmp_path):
        """If a feature is GA, a later 'preview' mention should not regress it."""
        tracker = self._make_tracker(tmp_path)
        tracker.track_item("Cosmos DB vector search generally available", "https://example.com/ga")
        event = tracker.track_item("Cosmos DB vector search in preview", "https://example.com/guide")
        assert event is None

    def test_deprecation_after_ga(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.track_item("Classic VMs generally available", "https://example.com/ga")
        event = tracker.track_item("Classic VMs retired", "https://example.com/retire")
        assert event is not None
        assert event.stage == "deprecated"
        assert event.is_progression is True
