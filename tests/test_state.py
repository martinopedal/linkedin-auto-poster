"""Tests for state management idempotency."""

from pathlib import Path

from src import StateStore


class TestStateStore:
    def _make_store(self, tmp_path: Path) -> StateStore:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "seen.json").write_text("{}")
        (data_dir / "published.json").write_text("{}")
        return StateStore(data_dir)

    def test_mark_seen_creates_entry(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_seen("https://example.com/article", "abc123", "Azure Updates")
        assert store.is_seen("https://example.com/article")

    def test_mark_seen_idempotent(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_seen("https://example.com/article", "abc123", "Azure Updates")
        store.mark_seen("https://example.com/article", "abc123", "Azure Updates")
        seen = store.load_seen()
        assert len(seen) == 1

    def test_not_seen_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        assert not store.is_seen("https://example.com/never-seen")

    def test_mark_seen_batch(self, tmp_path):
        store = self._make_store(tmp_path)
        items = [
            {"normalized_url": f"https://example.com/{i}", "title_hash": f"hash{i}", "source_feed": "test"}
            for i in range(5)
        ]
        store.mark_seen_batch(items)
        seen = store.load_seen()
        assert len(seen) == 5

    def test_mark_seen_batch_skips_existing(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_seen("https://example.com/0", "hash0", "test")
        items = [
            {"normalized_url": "https://example.com/0", "title_hash": "hash0", "source_feed": "test"},
            {"normalized_url": "https://example.com/1", "title_hash": "hash1", "source_feed": "test"},
        ]
        store.mark_seen_batch(items)
        seen = store.load_seen()
        assert len(seen) == 2

    def test_mark_published_creates_entry(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_published("draft-001", "urn:li:share:123", "https://example.com/article", pr_number=42)
        assert store.is_published("draft-001")

    def test_mark_published_idempotent(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_published("draft-001", "urn:li:share:123", "https://example.com/article")
        store.mark_published("draft-001", "urn:li:share:456", "https://example.com/article")
        published = store.load_published()
        assert len(published) == 1
        # First write wins
        assert published["draft-001"]["linkedin_urn"] == "urn:li:share:123"

    def test_not_published_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        assert not store.is_published("draft-never-published")

    def test_published_stores_metadata(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_published("draft-001", "urn:li:share:123", "https://example.com/article", pr_number=7)
        entry = store.load_published()["draft-001"]
        assert entry["linkedin_urn"] == "urn:li:share:123"
        assert entry["source_url"] == "https://example.com/article"
        assert entry["pr_number"] == 7
        assert "published_at" in entry

    def test_update_token_timestamp(self, tmp_path):
        store = self._make_store(tmp_path)
        store.update_token_timestamp()
        ts_file = tmp_path / "data" / "token_refreshed_at.txt"
        assert ts_file.exists()
        content = ts_file.read_text()
        assert "T" in content and "Z" in content

    def test_handles_missing_files_gracefully(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        store = StateStore(data_dir)
        assert store.load_seen() == {}
        assert store.load_published() == {}
