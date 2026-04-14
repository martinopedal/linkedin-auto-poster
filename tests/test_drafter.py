"""Tests for LinkedIn post drafter."""

from datetime import UTC, datetime

import frontmatter

from src.drafts.drafter import DraftPost, _make_draft_id, save_draft_to_file
from src.feeds.fetcher import NewsItem


class TestMakeDraftId:
    def test_includes_date_and_slug(self):
        item = NewsItem(
            title="AKS Karpenter support in preview",
            summary="test",
            link="https://example.com/aks-karpenter",
            published=datetime(2026, 4, 13, tzinfo=UTC),
        )
        draft_id = _make_draft_id(item)
        assert draft_id.startswith("2026-04-13-")
        assert "aks" in draft_id

    def test_includes_url_hash_for_uniqueness(self):
        item1 = NewsItem(
            title="AKS update", summary="t", link="https://example.com/a",
            published=datetime(2026, 4, 13, tzinfo=UTC),
        )
        item2 = NewsItem(
            title="AKS update", summary="t", link="https://example.com/b",
            published=datetime(2026, 4, 13, tzinfo=UTC),
        )
        assert _make_draft_id(item1) != _make_draft_id(item2)


class TestSaveDraftToFile:
    def test_creates_markdown_with_frontmatter(self, tmp_path):
        draft = DraftPost(
            draft_id="2026-04-13-test-draft-abc123",
            body="This is a test post.\n\n#Azure #AKS #Kubernetes",
            hashtags=["#Azure", "#AKS", "#Kubernetes"],
            pattern_used="observation",
            source_url="https://example.com/article",
            source_title="Test Article",
            score=7,
        )
        path = save_draft_to_file(draft, tmp_path)
        assert path.exists()
        assert path.suffix == ".md"

        post = frontmatter.load(str(path))
        assert post.metadata["draft_id"] == "2026-04-13-test-draft-abc123"
        assert post.metadata["publish"] is False
        assert post.metadata["score"] == 7
        assert post.metadata["pattern"] == "observation"
        assert "test post" in post.content

    def test_publish_defaults_to_false(self, tmp_path):
        draft = DraftPost(
            draft_id="test", body="body", hashtags=[], pattern_used="share",
            source_url="https://x.com", source_title="t", score=1,
        )
        path = save_draft_to_file(draft, tmp_path)
        post = frontmatter.load(str(path))
        assert post.metadata["publish"] is False
