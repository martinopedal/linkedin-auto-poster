"""Fetch significant releases from GitHub repos.

Tracks major and minor releases (skips patches) from configured repos.
Converts to NewsItem format for the existing scoring/drafting pipeline.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime

import requests

from src.feeds.fetcher import NewsItem

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _parse_semver(tag: str) -> tuple[int, int, int] | None:
    """Parse a semver tag like v1.2.3 or 1.2.3 into (major, minor, patch)."""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _significance_key(
    repo: str, version: tuple[int, int, int], min_type: str
) -> str:
    """Build a dedup key based on significance level."""
    major, minor, _ = version
    if min_type == "major":
        return f"{repo}@{major}"
    return f"{repo}@{major}.{minor}"


def fetch_github_releases(
    repos: list[dict],
    seen_keys: set[str] | None = None,
) -> list[NewsItem]:
    """Fetch significant releases from GitHub repos.

    Args:
        repos: List of dicts with 'repo', 'name', 'min_release_type'.
        seen_keys: Set of previously seen significance keys.

    Returns:
        List of NewsItem for significant new releases.
    """
    if seen_keys is None:
        seen_keys = set()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    items = []

    for repo_cfg in repos:
        repo = repo_cfg["repo"]
        name = repo_cfg.get("name", repo)
        min_type = repo_cfg.get("min_release_type", "minor")

        url = f"{GITHUB_API}/repos/{repo}/releases?per_page=10"
        try:
            resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                logger.warning("GitHub rate limited for %s, waiting %ds", repo, retry_after)
                import time
                time.sleep(min(retry_after, 120))
                resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code >= 500:
                logger.warning("GitHub 5xx for %s, retrying once", repo)
                import time
                time.sleep(5)
                resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code != 200:
                logger.warning(
                    "GitHub API %d for %s: %s",
                    resp.status_code, repo, resp.text[:200],
                )
                continue

            releases = resp.json()
        except Exception:
            logger.exception("Failed to fetch releases for %s", repo)
            continue

        for release in releases:
            if release.get("draft") or release.get("prerelease"):
                continue

            tag = release.get("tag_name", "")
            version = _parse_semver(tag)
            if not version:
                continue

            # Skip patches unless major/minor is new
            _, _, patch = version
            if min_type == "minor" and patch != 0:
                key = _significance_key(repo, version, min_type)
                if key in seen_keys:
                    continue

            key = _significance_key(repo, version, min_type)
            if key in seen_keys:
                continue

            published_str = release.get("published_at", "")
            try:
                published = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )
            except ValueError:
                published = datetime.now(UTC)

            body = release.get("body", "") or ""
            summary = body[:500] if body else f"{name} {tag} released"

            item = NewsItem(
                title=f"{name} {tag} released",
                summary=summary,
                link=release.get("html_url", ""),
                published=published,
                categories=["release", repo.split("/")[0]],
                source_feed=f"github:{repo}",
            )
            items.append(item)
            seen_keys.add(key)

            logger.info("New release: %s %s", repo, tag)

    return items
