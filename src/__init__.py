"""State management for seen articles and published posts.

State files live in data/seen.json and data/published.json on the main branch.
All operations are idempotent: adding an already-seen item is a no-op.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time as _time
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _file_lock(path, timeout=30):
    """Simple file-based lock for cross-process state safety."""
    lock_path = Path(str(path) + ".lock")
    start = _time.monotonic()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if _time.monotonic() - start > timeout:
                # Stale lock — force remove and retry
                logger.warning("Stale lock detected: %s, removing", lock_path)
                lock_path.unlink(missing_ok=True)
                continue
            _time.sleep(0.1)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


class StateStore:
    """Manages seen.json and published.json state files."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.seen_path = self.data_dir / "seen.json"
        self.published_path = self.data_dir / "published.json"

    # -- Unlocked helpers (caller already holds _file_lock) --

    def _load_unlocked(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Corrupted state file %s: %s", path, e)
            return {}

    def _save_unlocked(self, path: Path, data: dict) -> None:
        """Atomic write without acquiring lock (caller holds it)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise

    # -- Public locked wrappers (backward compat) --

    def _load(self, path: Path) -> dict:
        with _file_lock(path):
            return self._load_unlocked(path)

    def _save(self, path: Path, data: dict) -> None:
        """Atomic write with file lock."""
        with _file_lock(path):
            self._save_unlocked(path, data)

    # -- Seen state --

    def load_seen(self) -> dict:
        return self._load(self.seen_path)

    def is_seen(self, normalized_url: str) -> bool:
        seen = self.load_seen()
        return normalized_url in seen

    def mark_seen(self, normalized_url: str, title_hash: str, source_feed: str) -> None:
        """Mark an article as seen. Idempotent: skips if already present."""
        with _file_lock(self.seen_path):
            seen = self._load_unlocked(self.seen_path)
            if normalized_url in seen:
                return
            seen[normalized_url] = {
                "title_hash": title_hash,
                "first_seen": datetime.now(UTC).isoformat(),
                "source_feed": source_feed,
            }
            self._save_unlocked(self.seen_path, seen)

    def mark_seen_batch(self, items: list[dict]) -> None:
        """Mark multiple articles as seen in one write."""
        with _file_lock(self.seen_path):
            seen = self._load_unlocked(self.seen_path)
            now = datetime.now(UTC).isoformat()
            for item in items:
                url = item["normalized_url"]
                if url not in seen:
                    seen[url] = {
                        "title_hash": item["title_hash"],
                        "first_seen": now,
                        "source_feed": item["source_feed"],
                    }
            self._save_unlocked(self.seen_path, seen)

    # -- Published state --

    def load_published(self) -> dict:
        return self._load(self.published_path)

    def is_published(self, draft_id: str) -> bool:
        published = self.load_published()
        return draft_id in published

    def mark_published(
        self,
        draft_id: str,
        linkedin_urn: str,
        source_url: str,
        pr_number: int | None = None,
        summary: str = "",
        topic_tags: list[str] | None = None,
        tools_mentioned: list[str] | None = None,
        feature_slug: str | None = None,
    ) -> None:
        """Record a published draft. Idempotent: skips if already present."""
        with _file_lock(self.published_path):
            published = self._load_unlocked(self.published_path)
            if draft_id in published:
                return
            published[draft_id] = {
                "linkedin_urn": linkedin_urn,
                "published_at": datetime.now(UTC).isoformat(),
                "source_url": source_url,
                "pr_number": pr_number,
                "summary": summary[:200],
                "topic_tags": topic_tags or [],
                "tools_mentioned": tools_mentioned or [],
                "feature_slug": feature_slug or "",
            }
            self._save_unlocked(self.published_path, published)

    def get_recent_posts(self, limit: int = 20) -> list[dict]:
        """Get condensed summaries of recent published posts for LLM context."""
        published = self.load_published()
        entries = []
        for draft_id, data in published.items():
            entries.append({
                "draft_id": draft_id,
                "published_at": data.get("published_at", ""),
                "summary": data.get("summary", ""),
                "topic_tags": data.get("topic_tags", []),
                "tools_mentioned": data.get("tools_mentioned", []),
                "feature_slug": data.get("feature_slug", ""),
            })
        entries.sort(key=lambda x: x["published_at"], reverse=True)
        return entries[:limit]

    def get_relevant_posts(self, keywords: list[str], limit: int = 5) -> list[dict]:
        """Get posts relevant to the given keywords."""
        all_posts = self.get_recent_posts(limit=50)
        scored = []
        keywords_lower = [k.lower() for k in keywords]
        for post in all_posts:
            score = 0
            tags = [t.lower() for t in post.get("topic_tags", [])]
            tools = [t.lower() for t in post.get("tools_mentioned", [])]
            summary = post.get("summary", "").lower()
            for kw in keywords_lower:
                if kw in tags:
                    score += 3
                if kw in tools:
                    score += 2
                if kw in summary:
                    score += 1
            if score > 0:
                scored.append((score, post))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [post for _, post in scored[:limit]]

    def update_token_timestamp(self) -> None:
        """Update the token refresh timestamp file."""
        ts_path = self.data_dir / "token_refreshed_at.txt"
        with _file_lock(ts_path):
            ts_path.write_text(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
