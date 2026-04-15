"""Pending post queue for scheduled publishing."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

QUEUE_PATH = Path("data/pending-posts.json")
OSLO_TZ = ZoneInfo("Europe/Oslo")


def _load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    try:
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return []


def _save_queue(entries: list[dict]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def compute_publish_time(label: str) -> str:
    """Compute UTC publish time from a schedule label.

    Returns ISO format UTC datetime string.
    """
    now_oslo = datetime.now(OSLO_TZ)

    if label == "post-tomorrow":
        target = (now_oslo + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    elif label == "post-monday":
        days_ahead = (7 - now_oslo.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        target = (now_oslo + timedelta(days=days_ahead)).replace(hour=8, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unknown schedule label: {label}")

    return target.astimezone(ZoneInfo("UTC")).isoformat()


def queue_post(draft_id: str, draft_path: str, pr_number: int, label: str) -> None:
    """Add a post to the pending queue."""
    entries = _load_queue()
    publish_at = compute_publish_time(label)

    entries.append({
        "draft_id": draft_id,
        "draft_path": draft_path,
        "pr_number": pr_number,
        "label": label,
        "publish_at_utc": publish_at,
        "queued_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "status": "pending",
    })
    _save_queue(entries)
    logger.info("Queued %s for %s (label: %s)", draft_id, publish_at, label)


def get_due_posts() -> list[dict]:
    """Get posts that are due for publishing."""
    entries = _load_queue()
    now = datetime.now(ZoneInfo("UTC"))
    due = []
    for entry in entries:
        if entry.get("status") != "pending":
            continue
        publish_at = datetime.fromisoformat(entry["publish_at_utc"])
        if publish_at <= now:
            due.append(entry)
    return due


def mark_published(draft_id: str) -> None:
    """Mark a queued post as published."""
    entries = _load_queue()
    for entry in entries:
        if entry.get("draft_id") == draft_id:
            entry["status"] = "published"
            entry["published_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
    _save_queue(entries)


def mark_failed(draft_id: str, error: str) -> None:
    """Mark a queued post as failed."""
    entries = _load_queue()
    for entry in entries:
        if entry.get("draft_id") == draft_id:
            entry["status"] = "failed"
            entry["error"] = error
    _save_queue(entries)
