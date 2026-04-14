"""Tests for post-generation validator."""

from src.drafts.validator import sanitize_draft, validate_draft


def _make_post(length: int = 1000, hashtags: int = 4, banned: str = "", dash: str = "", emoji: str = "") -> str:
    """Build a synthetic post of a given length with controllable violations."""
    base = "AKS now supports Karpenter for node autoscaling. "
    body = (base * (length // len(base) + 1))[:length - 60]
    tags = " ".join([f"#Tag{i}" for i in range(hashtags)])
    return f"{body}{banned}{dash}{emoji}\n\n{tags}"


class TestValidateDraft:
    def test_valid_post_passes(self):
        text = _make_post(1000, 4)
        result = validate_draft(text)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_too_short_fails(self):
        text = _make_post(500, 4)
        result = validate_draft(text)
        assert not result.is_valid
        assert any("short" in e.lower() for e in result.errors)

    def test_too_long_fails(self):
        text = _make_post(2000, 4)
        result = validate_draft(text)
        assert not result.is_valid
        assert any("long" in e.lower() for e in result.errors)

    def test_too_few_hashtags_fails(self):
        text = _make_post(1000, 1)
        result = validate_draft(text)
        assert not result.is_valid
        assert any("few hashtags" in e.lower() for e in result.errors)

    def test_too_many_hashtags_fails(self):
        text = _make_post(1000, 8)
        result = validate_draft(text)
        assert not result.is_valid
        assert any("many hashtags" in e.lower() for e in result.errors)

    def test_banned_phrase_fails(self):
        text = _make_post(1000, 4, banned=" This is a game-changer for the industry.")
        result = validate_draft(text)
        assert not result.is_valid
        assert any("banned phrase" in e.lower() for e in result.errors)

    def test_em_dash_fails(self):
        text = _make_post(1000, 4, dash=" This is great \u2014 really great.")
        result = validate_draft(text)
        assert not result.is_valid
        assert any("em dash" in e.lower() or "en dash" in e.lower() for e in result.errors)

    def test_en_dash_fails(self):
        text = _make_post(1000, 4, dash=" Pages 10\u201320 are relevant.")
        result = validate_draft(text)
        assert not result.is_valid

    def test_emoji_fails(self):
        text = _make_post(1000, 4, emoji=" \U0001F680")
        result = validate_draft(text)
        assert not result.is_valid
        assert any("emoji" in e.lower() for e in result.errors)

    def test_source_url_warning_when_missing(self):
        text = _make_post(1000, 4)
        result = validate_draft(text, source_url="https://example.com/article")
        assert any("source url" in w.lower() for w in result.warnings)

    def test_multiple_violations_all_reported(self):
        text = _make_post(
            500, 1, banned=" I'm excited to share this game-changer!", dash=" \u2014", emoji=" \U0001F600"
        )
        result = validate_draft(text)
        assert not result.is_valid
        assert len(result.errors) >= 4


class TestSanitizeDraft:
    def test_em_dash_replaced(self):
        text = "AKS now supports Karpenter \u2014 a great feature."
        result = sanitize_draft(text)
        assert "\u2014" not in result
        assert "," in result

    def test_en_dash_replaced(self):
        text = "Pages 10\u201320 are relevant."
        result = sanitize_draft(text)
        assert "\u2013" not in result

    def test_emoji_removed(self):
        text = "Great news \U0001F680 for the community!"
        result = sanitize_draft(text)
        assert "\U0001F680" not in result
        assert "Great news" in result

    def test_over_length_trimmed_at_sentence(self):
        # Build text > 1400 chars with clear sentence boundaries
        sentence = "AKS now supports Karpenter for autoscaling. "
        text = sentence * 40  # ~1800 chars
        assert len(text) > 1400
        result = sanitize_draft(text)
        assert len(result) <= 1400
        # Should end at a sentence boundary
        assert result.rstrip().endswith(".")

    def test_clean_text_unchanged(self):
        text = "AKS now supports Karpenter for node autoscaling."
        result = sanitize_draft(text)
        assert result == text

    def test_multiple_fixes_combined(self):
        text = "Great \U0001F680 feature \u2014 really nice."
        result = sanitize_draft(text)
        assert "\U0001F680" not in result
        assert "\u2014" not in result
