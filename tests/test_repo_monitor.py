import tempfile
import unittest
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.feeds.repo_monitor import _load_known_repos, _save_known_repos, check_new_repos


class TestRepoMonitor(unittest.TestCase):
    def test_load_empty(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("src.feeds.repo_monitor.STATE_FILE", Path(d) / "known.json"):
                assert _load_known_repos() == set()

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "known.json"
            with patch("src.feeds.repo_monitor.STATE_FILE", p):
                _save_known_repos({"a/b", "c/d"})
                loaded = _load_known_repos()
                assert loaded == {"a/b", "c/d"}

    @patch("src.feeds.repo_monitor.requests.get")
    @patch("src.feeds.repo_monitor._get_github_user", return_value="testuser")
    def test_detects_new_repo(self, mock_user, mock_get):
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{
                "full_name": "testuser/new-thing",
                "name": "new-thing",
                "description": "A new module",
                "html_url": "https://github.com/testuser/new-thing",
                "language": "HCL",
                "created_at": now,
                "fork": False,
            }],
        )
        with tempfile.TemporaryDirectory() as d:
            with patch("src.feeds.repo_monitor.STATE_FILE", Path(d) / "known.json"):
                repos = check_new_repos(days_back=1)
                assert len(repos) == 1
                assert repos[0]["name"] == "new-thing"

    @patch("src.feeds.repo_monitor.requests.get")
    @patch("src.feeds.repo_monitor._get_github_user", return_value="testuser")
    def test_skips_known_repos(self, mock_user, mock_get):
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{
                "full_name": "testuser/old-repo",
                "name": "old-repo",
                "description": "",
                "html_url": "",
                "language": "",
                "created_at": now,
                "fork": False,
            }],
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "known.json"
            p.write_text('["testuser/old-repo"]')
            with patch("src.feeds.repo_monitor.STATE_FILE", p):
                repos = check_new_repos(days_back=1)
                assert len(repos) == 0

    @patch("src.feeds.repo_monitor.requests.get")
    @patch("src.feeds.repo_monitor._get_github_user", return_value="testuser")
    def test_skips_forks(self, mock_user, mock_get):
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{
                "full_name": "testuser/forked",
                "name": "forked",
                "description": "",
                "html_url": "",
                "language": "",
                "created_at": now,
                "fork": True,
            }],
        )
        with tempfile.TemporaryDirectory() as d:
            with patch("src.feeds.repo_monitor.STATE_FILE", Path(d) / "known.json"):
                repos = check_new_repos(days_back=1)
                assert len(repos) == 0
