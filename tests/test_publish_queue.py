from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.publish_queue import (
    _load_queue,
    compute_publish_time,
    get_due_posts,
    mark_published,
    queue_post,
)


class TestComputePublishTime:
    def test_post_tomorrow(self):
        result = compute_publish_time("post-tomorrow")
        dt = datetime.fromisoformat(result)
        assert dt > datetime.now(ZoneInfo("UTC"))

    def test_post_monday(self):
        result = compute_publish_time("post-monday")
        dt = datetime.fromisoformat(result)
        oslo = dt.astimezone(ZoneInfo("Europe/Oslo"))
        assert oslo.weekday() == 0  # Monday
        assert oslo.hour == 8

    def test_invalid_label(self):
        with pytest.raises(ValueError):
            compute_publish_time("invalid")


class TestQueue:
    def test_queue_and_retrieve(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.publish_queue.QUEUE_PATH", tmp_path / "queue.json")
        queue_post("test-1", "drafts/test.md", 42, "post-tomorrow")
        entries = _load_queue()
        assert len(entries) == 1
        assert entries[0]["status"] == "pending"

    def test_mark_published(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.publish_queue.QUEUE_PATH", tmp_path / "queue.json")
        queue_post("test-1", "drafts/test.md", 42, "post-tomorrow")
        mark_published("test-1")
        entries = _load_queue()
        assert entries[0]["status"] == "published"

    def test_get_due_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.publish_queue.QUEUE_PATH", tmp_path / "queue.json")
        assert get_due_posts() == []
