"""Feature lifecycle tracker.

Tracks Azure features across their lifecycle stages (announced, private preview,
public preview, GA, deprecated). When a feature progresses from one stage to another,
it is flagged as high-priority for posting.

State is stored in data/features.json with the following structure:
{
    "feature-slug": {
        "name": "Feature Name",
        "first_seen": "2026-01-15T06:00:00Z",
        "stages": [
            {"stage": "preview", "date": "2026-01-15T06:00:00Z", "source_url": "..."},
            {"stage": "ga", "date": "2026-04-10T06:00:00Z", "source_url": "..."}
        ],
        "current_stage": "ga",
        "posted_stages": ["preview"],
        "last_posted": "2026-01-16T06:00:00Z"
    }
}
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src import _file_lock

logger = logging.getLogger(__name__)

STAGE_ORDER = {
    "announced": 0,
    "private_preview": 1,
    "public_preview": 2,
    "preview": 2,
    "ga": 3,
    "generally_available": 3,
    "deprecated": 4,
    "retired": 4,
}

STAGE_LABELS = {
    0: "announced",
    1: "private_preview",
    2: "preview",
    3: "ga",
    4: "deprecated",
}

# Patterns to detect stage from title/summary text
# ORDER MATTERS: specific patterns must come before general ones
STAGE_PATTERNS = [
    (re.compile(r"\bgenerally\s+available\b", re.IGNORECASE), "ga"),
    (re.compile(r"\bnow\s+available\b", re.IGNORECASE), "ga"),
    (re.compile(r"\b(?:is|are)\s+(?:now\s+)?GA\b", re.IGNORECASE), "ga"),
    (re.compile(r"\bGA\b", re.IGNORECASE), "ga"),
    (re.compile(r"\bprivate\s+preview\b", re.IGNORECASE), "private_preview"),
    (re.compile(r"\bpublic\s+preview\b", re.IGNORECASE), "preview"),
    (re.compile(r"\bin\s+preview\b", re.IGNORECASE), "preview"),
    (re.compile(r"\bpreview\b", re.IGNORECASE), "preview"),
    (re.compile(r"\bretir(?:ed|ing|ement)\b", re.IGNORECASE), "deprecated"),
    (re.compile(r"\bdeprecate[ds]?\b", re.IGNORECASE), "deprecated"),
]


def detect_stage(text: str) -> str | None:
    """Detect the lifecycle stage from article text. Returns None if unclear."""
    for pattern, stage in STAGE_PATTERNS:
        if pattern.search(text):
            return stage
    return None


def normalize_feature_name(title: str) -> str:
    """Extract a normalized feature slug from an article title.

    Order: strip stage keywords, strip punctuation, strip prefixes,
    strip version numbers, strip region qualifiers, strip filler words, slugify.
    """
    cleaned = title
    # 1. Remove region qualifiers in parens (before punctuation strip)
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    # 2. Remove stage keywords
    for pattern, _ in STAGE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    # 3. Remove punctuation early (so prefix strip works after "Generally Available: Azure ...")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # 3. Remove common prefixes (non-anchored to catch mid-string too)
    cleaned = re.sub(r"\b(?:Azure|Microsoft)\b", "", cleaned, flags=re.IGNORECASE)
    # 5. Remove version numbers (v1, v2.0, 1.2.3, etc.)
    cleaned = re.sub(r"\bv?\d+(?:\.\d+)*\b", "", cleaned)
    # 6. Remove filler and context words
    cleaned = re.sub(
        r"\b(?:is|are|now|in|the|for|with|and|on|to|will|be|has|have|new|update|announcement|guide|blog|post)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # 7. Normalize whitespace and make slug
    cleaned = cleaned.strip()
    cleaned = re.sub(r"\s+", "-", cleaned).lower()
    cleaned = cleaned.strip("-")
    # Remove consecutive dashes from stripped words
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:80] if cleaned else "unknown-feature"


class FeatureTracker:
    """Tracks feature lifecycle stages for intelligent posting decisions."""

    def __init__(self, data_dir: str | Path = "data"):
        self.path = Path(data_dir) / "features.json"

    # -- Unlocked helpers (caller already holds _file_lock) --

    def _load_unlocked(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Corrupted state file %s: %s", self.path, e)
            return {}

    def _save_unlocked(self, data: dict) -> None:
        """Atomic write without acquiring lock (caller holds it)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise

    # -- Public locked wrappers (backward compat) --

    def _load(self) -> dict:
        with _file_lock(self.path):
            return self._load_unlocked()

    def _save(self, data: dict) -> None:
        """Atomic write with file lock."""
        with _file_lock(self.path):
            self._save_unlocked(data)

    def track_item(
        self,
        title: str,
        source_url: str,
        published_date: str | None = None,
    ) -> FeatureEvent | None:
        """Track a news item and determine if it represents a stage progression.

        Returns a FeatureEvent if the item represents a new or progressed feature,
        or None if it is a repeat of an already-tracked stage.
        """
        text = title
        stage = detect_stage(text)
        if stage is None:
            return None

        slug = normalize_feature_name(title)
        now = published_date or datetime.now(UTC).isoformat()

        with _file_lock(self.path):
            features = self._load_unlocked()

            if slug not in features:
                # Brand new feature, first time we see it
                features[slug] = {
                    "name": title,
                    "first_seen": now,
                    "stages": [{"stage": stage, "date": now, "source_url": source_url}],
                    "current_stage": stage,
                    "posted_stages": [],
                    "last_posted": None,
                }
                self._save_unlocked(features)
                return FeatureEvent(
                    slug=slug,
                    name=title,
                    stage=stage,
                    is_new=True,
                    is_progression=False,
                    previous_stage=None,
                    first_seen=now,
                    priority_boost=self._priority_boost(stage, is_new=True, is_progression=False),
                )

            feature = features[slug]
            current_order = STAGE_ORDER.get(feature["current_stage"], 0)
            new_order = STAGE_ORDER.get(stage, 0)

            if new_order <= current_order:
                # Same or earlier stage, not a progression
                return None

            # Stage progression detected
            previous_stage = feature["current_stage"]
            feature["stages"].append({"stage": stage, "date": now, "source_url": source_url})
            feature["current_stage"] = stage
            features[slug] = feature
            self._save_unlocked(features)

        return FeatureEvent(
            slug=slug,
            name=feature["name"],
            stage=stage,
            is_new=False,
            is_progression=True,
            previous_stage=previous_stage,
            first_seen=feature["first_seen"],
            priority_boost=self._priority_boost(stage, is_new=False, is_progression=True),
        )

    def mark_posted(self, slug: str, stage: str) -> None:
        """Record that a post was made for this feature at this stage."""
        with _file_lock(self.path):
            features = self._load_unlocked()
            if slug not in features:
                return
            feature = features[slug]
            if stage not in feature["posted_stages"]:
                feature["posted_stages"].append(stage)
            feature["last_posted"] = datetime.now(UTC).isoformat()
            features[slug] = feature
            self._save_unlocked(features)

    def was_posted_at_stage(self, slug: str, stage: str) -> bool:
        """Check if a feature was already posted about at a given stage."""
        features = self._load()
        if slug not in features:
            return False
        return stage in features[slug].get("posted_stages", [])

    def get_feature(self, slug: str) -> dict | None:
        """Get full feature tracking data."""
        features = self._load()
        return features.get(slug)

    def get_progression_summary(self, slug: str) -> str | None:
        """Get a human-readable summary of a feature's lifecycle for use in posts.

        Example: "First announced in preview on Jan 15, now reaching GA after 3 months."
        """
        feature = self.get_feature(slug)
        if not feature or len(feature["stages"]) < 2:
            return None

        stages = feature["stages"]
        first = stages[0]
        latest = stages[-1]

        try:
            first_date = datetime.fromisoformat(first["date"])
            latest_date = datetime.fromisoformat(latest["date"])
            days_between = (latest_date - first_date).days

            if days_between < 30:
                duration = f"{days_between} days"
            else:
                months = days_between // 30
                duration = f"{months} month{'s' if months != 1 else ''}"

            return (
                f"First seen in {first['stage']} on {first_date.strftime('%b %d')}, "
                f"now reaching {latest['stage']} after {duration}."
            )
        except (ValueError, KeyError):
            return None

    @staticmethod
    def _priority_boost(stage: str, is_new: bool, is_progression: bool) -> int:
        """Calculate a bounded priority boost for the scoring system.

        Capped at 6 so lifecycle signals influence but never dominate topic relevance.
        Brand new GA features and preview-to-GA progressions get the highest boost.
        """
        boost = 0

        # Stage-based boost
        if stage == "ga":
            boost += 3
        elif stage in ("preview", "public_preview"):
            boost += 1
        elif stage == "deprecated":
            boost += 2

        # New feature boost
        if is_new:
            boost += 2

        # Progression boost (this is a story with context)
        if is_progression:
            boost += 3

        return min(boost, 6)


class FeatureEvent:
    """Represents a detected feature lifecycle event."""

    def __init__(
        self,
        slug: str,
        name: str,
        stage: str,
        is_new: bool,
        is_progression: bool,
        previous_stage: str | None,
        first_seen: str,
        priority_boost: int,
    ):
        self.slug = slug
        self.name = name
        self.stage = stage
        self.is_new = is_new
        self.is_progression = is_progression
        self.previous_stage = previous_stage
        self.first_seen = first_seen
        self.priority_boost = priority_boost

    def __repr__(self) -> str:
        if self.is_progression:
            return f"FeatureEvent({self.slug}: {self.previous_stage} -> {self.stage}, boost=+{self.priority_boost})"
        return f"FeatureEvent({self.slug}: new {self.stage}, boost=+{self.priority_boost})"
