"""Tests for GitHub releases fetcher."""

import unittest
from unittest.mock import patch

import responses

from src.feeds.github_releases import (
    GITHUB_API,
    _parse_semver,
    _significance_key,
    fetch_github_releases,
)


class TestParseSemver(unittest.TestCase):
    def test_with_v_prefix(self):
        assert _parse_semver("v1.2.3") == (1, 2, 3)

    def test_without_v_prefix(self):
        assert _parse_semver("1.2.3") == (1, 2, 3)

    def test_large_numbers(self):
        assert _parse_semver("v10.20.300") == (10, 20, 300)

    def test_zeros(self):
        assert _parse_semver("v0.0.0") == (0, 0, 0)

    def test_invalid_tag_returns_none(self):
        assert _parse_semver("latest") is None

    def test_partial_version_returns_none(self):
        assert _parse_semver("v1.2") is None

    def test_non_numeric_returns_none(self):
        assert _parse_semver("v1.2.beta") is None

    def test_empty_string_returns_none(self):
        assert _parse_semver("") is None

    def test_extra_suffix_still_parses(self):
        # re.match only matches the start, so extra chars are fine
        result = _parse_semver("v1.2.3-rc1")
        assert result == (1, 2, 3)


class TestSignificanceKey(unittest.TestCase):
    def test_minor_mode(self):
        key = _significance_key("org/repo", (2, 5, 0), "minor")
        assert key == "org/repo@2.5"

    def test_major_mode(self):
        key = _significance_key("org/repo", (2, 5, 0), "major")
        assert key == "org/repo@2"

    def test_minor_mode_with_patch(self):
        key = _significance_key("org/repo", (1, 0, 3), "minor")
        assert key == "org/repo@1.0"

    def test_major_mode_ignores_minor(self):
        key = _significance_key("org/repo", (3, 9, 1), "major")
        assert key == "org/repo@3"


def _make_release(tag, draft=False, prerelease=False, published_at=None, body="Release notes"):
    """Helper to build a GitHub release payload."""
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": published_at or "2026-06-01T12:00:00Z",
        "html_url": f"https://github.com/org/repo/releases/tag/{tag}",
        "body": body,
    }


class TestFetchGithubReleases(unittest.TestCase):
    REPO_CFG = [{"repo": "org/repo", "name": "MyProject", "min_release_type": "minor"}]

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_normal_release_list(self):
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(
            responses.GET, url, json=[_make_release("v2.0.0"), _make_release("v1.0.0")], status=200,
        )
        items = fetch_github_releases(self.REPO_CFG)
        assert len(items) == 2
        assert items[0].title == "MyProject v2.0.0 released"
        assert items[0].source_feed == "github:org/repo"
        assert "release" in items[0].categories

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_skips_drafts_and_prereleases(self):
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(
            responses.GET, url, json=[
                _make_release("v2.0.0", draft=True),
                _make_release("v1.1.0", prerelease=True),
                _make_release("v1.0.0"),
            ], status=200,
        )
        items = fetch_github_releases(self.REPO_CFG)
        assert len(items) == 1
        assert items[0].title == "MyProject v1.0.0 released"

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_skips_patches_when_minor(self):
        """Patch releases (x.y.z where z!=0) should be skipped when min_type is minor,
        unless the major.minor hasn't been seen yet."""
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(
            responses.GET, url, json=[
                _make_release("v2.0.0"),
                _make_release("v2.0.1"),  # patch of already-seen 2.0 -> skip
                _make_release("v1.1.0"),
            ], status=200,
        )
        items = fetch_github_releases(self.REPO_CFG)
        titles = [i.title for i in items]
        assert "MyProject v2.0.0 released" in titles
        assert "MyProject v1.1.0 released" in titles
        assert "MyProject v2.0.1 released" not in titles

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_handles_404(self):
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(responses.GET, url, json={"message": "Not Found"}, status=404)
        items = fetch_github_releases(self.REPO_CFG)
        assert items == []

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_handles_rate_limit(self):
        """429 triggers a retry; if both fail, returns empty."""
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(responses.GET, url, json={"message": "rate limit"}, status=429, headers={"Retry-After": "0"})
        responses.add(responses.GET, url, json={"message": "rate limit"}, status=429, headers={"Retry-After": "0"})
        items = fetch_github_releases(self.REPO_CFG)
        assert items == []

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_handles_empty_response(self):
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(responses.GET, url, json=[], status=200)
        items = fetch_github_releases(self.REPO_CFG)
        assert items == []

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_seen_keys_prevents_duplicates(self):
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(responses.GET, url, json=[_make_release("v1.0.0")], status=200)
        seen = {"org/repo@1.0"}
        items = fetch_github_releases(self.REPO_CFG, seen_keys=seen)
        assert items == []

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_invalid_tag_skipped(self):
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(
            responses.GET, url, json=[_make_release("latest"), _make_release("v1.0.0")], status=200,
        )
        items = fetch_github_releases(self.REPO_CFG)
        assert len(items) == 1
        assert items[0].title == "MyProject v1.0.0 released"

    @responses.activate
    @patch.dict("os.environ", {"GITHUB_TOKEN": ""}, clear=False)
    def test_empty_body_uses_fallback_summary(self):
        url = f"{GITHUB_API}/repos/org/repo/releases?per_page=10"
        responses.add(
            responses.GET, url, json=[_make_release("v3.0.0", body="")], status=200,
        )
        items = fetch_github_releases(self.REPO_CFG)
        assert items[0].summary == "MyProject v3.0.0 released"
