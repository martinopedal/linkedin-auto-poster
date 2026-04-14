"""Monitor GitHub repos for new creations and generate showcase drafts."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

STATE_FILE = Path("data/known_repos.json")


def _get_github_user() -> str:
    """Get the GitHub username from env var or token."""
    user = os.environ.get("GITHUB_USER")
    if user:
        return user
    # Could also introspect from GITHUB_TOKEN via API, but env var is simpler
    return os.environ.get("GITHUB_ACTOR", "")


def _load_known_repos() -> set[str]:
    """Load set of known repo full_names."""
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, ValueError):
        return set()


def _save_known_repos(repos: set[str]) -> None:
    """Save known repos set."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(sorted(repos), indent=2), encoding="utf-8"
    )


def check_new_repos(days_back: int = 7) -> list[dict]:
    """Check for repos created in the last N days.

    Returns list of dicts with: name, full_name, description, html_url, language, created_at
    """
    github_user = _get_github_user()
    if not github_user:
        logger.warning("No GITHUB_USER set and cannot determine username. Skipping repo check.")
        return []

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    cutoff = datetime.now(UTC) - timedelta(days=days_back)
    known = _load_known_repos()

    try:
        resp = requests.get(
            f"https://api.github.com/users/{github_user}/repos",
            headers=headers,
            params={"sort": "created", "direction": "desc", "per_page": 10},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to check repos: %s", e)
        return []

    new_repos = []
    all_names = set(known)

    for repo in resp.json():
        full_name = repo.get("full_name", "")
        all_names.add(full_name)

        if full_name in known:
            continue

        created_str = repo.get("created_at", "")
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        if created < cutoff:
            continue

        # Skip forks and private repos (we post about our own work)
        if repo.get("fork"):
            continue

        new_repos.append({
            "name": repo.get("name", ""),
            "full_name": full_name,
            "description": repo.get("description", "") or "",
            "html_url": repo.get("html_url", ""),
            "language": repo.get("language", "") or "",
            "created_at": created_str,
        })
        logger.info("New repo detected: %s", full_name)

    _save_known_repos(all_names)
    return new_repos
