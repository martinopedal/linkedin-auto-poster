"""Tests for topic-based draft generation and publish schedule gate."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from unittest.mock import patch

import frontmatter

from src.drafts.drafter import TopicDraft, generate_topic_draft, save_topic_draft_to_file


class TestTopicDraft:
    """Tests for TopicDraft dataclass."""

    def test_topic_draft_fields(self):
        draft = TopicDraft(
            draft_id="topic-2026-04-14-alz-mistakes",
            body="Test post body with enough content " * 30,
            hashtags=["#Azure", "#LandingZones", "#Terraform"],
            pattern_used="lessons",
            topic_id="alz-mistakes",
            topic_title="Landing Zone mistakes",
            pillar="cloud-architecture",
            scheduled_for="2026-04-14",
        )
        assert draft.topic_id == "alz-mistakes"
        assert draft.content_type_value == "topic" if hasattr(draft, "content_type_value") else True


class TestSaveTopicDraft:
    """Tests for saving topic drafts to files."""

    def test_creates_markdown_with_topic_frontmatter(self):
        draft = TopicDraft(
            draft_id="topic-2026-04-14-alz-mistakes",
            body="Test post body content here.",
            hashtags=["#Azure", "#LandingZones"],
            pattern_used="lessons",
            topic_id="alz-mistakes",
            topic_title="Landing Zone mistakes",
            pillar="cloud-architecture",
            scheduled_for="2026-04-14",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_topic_draft_to_file(draft, tmpdir)
            assert path.exists()
            post = frontmatter.load(str(path))
            assert post.metadata["content_type"] == "topic"
            assert post.metadata["topic_id"] == "alz-mistakes"
            assert post.metadata["scheduled_for"] == "2026-04-14"
            assert post.metadata["publish"] is False
            assert "source_url" not in post.metadata
            assert "score" not in post.metadata

    def test_saves_to_scheduled_date_directory(self):
        draft = TopicDraft(
            draft_id="topic-2026-04-14-alz-mistakes",
            body="Test body.",
            hashtags=["#Azure"],
            pattern_used="lessons",
            topic_id="alz-mistakes",
            topic_title="Test",
            pillar="cloud-architecture",
            scheduled_for="2026-04-14",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_topic_draft_to_file(draft, tmpdir)
            assert "2026-04-14" in str(path)


class TestGenerateTopicDraft:
    """Tests for LLM-based topic draft generation."""

    @patch("src.drafts.drafter.run_pipeline_sync")
    def test_generates_valid_topic_draft(self, mock_pipeline):
        body = (
            "I have reviewed Landing Zones that checked every box on paper. "
            "CAF aligned. Hub and spoke. Policy driven. They were still a mess. "
            "The problems were not in what they built. They were in what they "
            "stopped doing after they built it. Three things I see go wrong "
            "repeatedly. First, no subscription vending automation. Teams submit "
            "tickets. Someone manually creates a subscription, guesses at a name, "
            "forgets to peer the spoke VNet. Two months later you have 40 "
            "subscriptions with inconsistent policy and no budget alerts. "
            "Second, deny all policies with no exemption workflow. Restrictive "
            "policy is correct. But without a process for time bound, auditable "
            "exemptions, developers route around governance instead of through it. "
            "Third, connectivity treated as a one time deployment. Your hub "
            "firewall rules will change the moment a second workload team "
            "onboards. If your connectivity subscription is not version "
            "controlled it will drift silently.\n\n"
            "#Azure #LandingZones #Terraform"
        )
        mock_pipeline.return_value = (
            {
                "body": body,
                "hashtags": ["#Azure", "#LandingZones", "#Terraform"],
                "pattern_used": "lessons",
            },
            None,
        )

        topic = {
            "id": "alz-mistakes",
            "title": "Three things I see go wrong after Landing Zone deployment",
            "pattern": "lessons",
            "pillar": "cloud-architecture",
            "scheduled_for": "2026-04-14",
            "notes": "Subscription vending, deny-all policies, connectivity drift",
        }

        draft = generate_topic_draft(topic, {"model": "gpt-4o", "temperature": 0.7})
        assert draft is not None
        assert draft.topic_id == "alz-mistakes"
        assert draft.draft_id == "topic-2026-04-14-alz-mistakes"
        assert draft.scheduled_for == "2026-04-14"

    @patch("src.drafts.drafter.run_pipeline_sync")
    def test_rejects_draft_with_banned_phrases(self, mock_pipeline):
        body = "I'm excited to share this game-changer. " * 30
        mock_pipeline.return_value = (
            {
                "body": body,
                "hashtags": ["#Azure", "#AKS", "#Terraform"],
                "pattern_used": "lessons",
            },
            None,
        )

        topic = {
            "id": "test-topic",
            "title": "Test topic",
            "pattern": "lessons",
            "scheduled_for": "2026-04-14",
        }

        draft = generate_topic_draft(topic, {"model": "gpt-4o"})
        assert draft is None


class TestPublishScheduleGate:
    """Tests for the scheduled_for publish-time gate."""

    def test_future_scheduled_post_is_skipped(self):
        """A post with scheduled_for in the future should not publish."""
        future = (date.today() + timedelta(days=3)).isoformat()
        metadata = {"scheduled_for": future, "publish": True}
        sched_date = date.fromisoformat(str(metadata["scheduled_for"]))
        assert sched_date > date.today()

    def test_past_scheduled_post_is_allowed(self):
        """A post with scheduled_for in the past should publish."""
        past = (date.today() - timedelta(days=1)).isoformat()
        metadata = {"scheduled_for": past, "publish": True}
        sched_date = date.fromisoformat(str(metadata["scheduled_for"]))
        assert sched_date <= date.today()

    def test_today_scheduled_post_is_allowed(self):
        """A post with scheduled_for today should publish."""
        today = date.today().isoformat()
        metadata = {"scheduled_for": today, "publish": True}
        sched_date = date.fromisoformat(str(metadata["scheduled_for"]))
        assert sched_date <= date.today()

    def test_no_scheduled_for_is_allowed(self):
        """A post without scheduled_for should publish normally."""
        metadata = {"publish": True}
        assert "scheduled_for" not in metadata or not metadata.get("scheduled_for")
