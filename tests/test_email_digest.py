"""Tests for email digest generation."""

import json
from unittest.mock import MagicMock, patch

from src.email_digest import (
    _build_html_digest,
    _build_text_digest,
    _load_candidates,
    send_digest,
)


class TestBuildDigest:
    def test_html_digest_with_items(self):
        items = [
            {
                "title": "AKS Update",
                "score": 15,
                "link": "https://example.com",
                "feed_name": "Azure Blog",
                "summary": "New AKS feature",
                "published": "2026-04-14",
            },
            {
                "title": "Minor Fix",
                "score": 3,
                "link": "https://example.com/2",
                "feed_name": "K8s Blog",
                "summary": "Bug fix",
                "published": "2026-04-14",
            },
        ]
        html = _build_html_digest(items, "2026-04-14")
        assert "AKS Update" in html
        assert "Minor Fix" in html
        assert "score: 15" in html
        assert "2 items" in html

    def test_html_digest_empty(self):
        html = _build_html_digest([], "2026-04-14")
        assert "No news items" in html

    def test_text_digest_sorted_by_score(self):
        items = [
            {"title": "Low", "score": 2, "link": "https://a.com"},
            {"title": "High", "score": 20, "link": "https://b.com"},
        ]
        text = _build_text_digest(items, "2026-04-14")
        high_pos = text.index("High")
        low_pos = text.index("Low")
        assert high_pos < low_pos

    def test_text_digest_empty(self):
        text = _build_text_digest([], "2026-04-14")
        assert "No news items" in text


class TestLoadCandidates:
    def test_load_valid(self, tmp_path):
        f = tmp_path / "candidates.json"
        f.write_text(json.dumps([{"title": "Test", "score": 5}]))
        items = _load_candidates(str(f))
        assert len(items) == 1

    def test_load_missing(self):
        items = _load_candidates("C:\\nonexistent\\path.json")
        assert items == []

    def test_load_corrupt(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json")
        items = _load_candidates(str(f))
        assert items == []


class TestSendDigest:
    def test_no_recipients_returns_false(self, monkeypatch):
        monkeypatch.delenv("EMAIL_RECIPIENTS", raising=False)
        assert send_digest() is False

    def test_no_smtp_host_returns_false(self, monkeypatch):
        monkeypatch.setenv("EMAIL_RECIPIENTS", "test@example.com")
        monkeypatch.delenv("SMTP_HOST", raising=False)
        assert send_digest() is False

    @patch("src.email_digest.smtplib.SMTP")
    def test_send_success(self, mock_smtp, monkeypatch, tmp_path):
        monkeypatch.setenv("EMAIL_RECIPIENTS", "a@b.com,c@d.com")
        monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
        monkeypatch.setenv("SMTP_USERNAME", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")

        f = tmp_path / "candidates.json"
        f.write_text(json.dumps([{"title": "Test", "score": 5}]))

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = send_digest(candidates_path=str(f))
        assert result is True
