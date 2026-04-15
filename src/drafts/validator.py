"""Post-generation validation for LinkedIn drafts.

Programmatic checks that catch format violations the LLM misses.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

BANNED_PHRASES = [
    "leveraging", "driving", "unlocking", "in today's landscape",
    "game-changer", "deep dive into", "at the end of the day",
    "it goes without saying", "comprehensive", "robust", "cutting-edge",
    "I'm excited to", "Thrilled to", "journey",
    "in today's world", "as we all know",
    "here is why this matters", "here's why this matters",
    "key takeaways", "whether you are", "whether you're",
    "the reality is", "the truth is", "the fact is",
    "it's worth noting", "one thing is clear", "here's the thing",
    "the takeaway", "unpopular opinion", "hot take",
    "humbled to", "grateful to announce",
    "curious how others", "what are you seeing",
    "at scale", "enterprise-grade", "production-ready", "future-proof",
    "AI-powered", "seamless integration", "seamlessly",
    "modernizing", "digital transformation",
    "not only", "elevate", "empower", "accelerate",
    "streamline", "optimize", "now more than ever",
    "across industries", "for teams of all sizes",
    "agree?", "thoughts?",
    "the pattern across", "this is the pattern",
    "that experience shaped", "that background gave me",
    "here is what I learned", "this is why", "that is why",
    "one lesson I still use", "sounds simple",
    "the hard part is", "changed how I think about",
    "my bet is", "it is not about",
]

# Customer and company names are loaded from data/blocked-names.txt (gitignored).
# One name per line. Checked case-insensitively as whole words.
BLOCKED_NAMES_PATH = Path(__file__).parent.parent.parent / "data" / "blocked-names.txt"


def _load_blocked_names() -> list[str]:
    """Load blocked customer names from external file."""
    if not BLOCKED_NAMES_PATH.exists():
        return []
    lines = BLOCKED_NAMES_PATH.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]

# PII and confidential patterns
PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "email address"),
    (re.compile(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{3}\b"), "phone number pattern"),
    (re.compile(r"\b\d{11}\b"), "Norwegian national ID (fodselsnummer)"),
    (re.compile(r"\b\d{9}\b"), "Norwegian org number"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "IP address"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "UUID/subscription ID"),
    (re.compile(r"(?i)\b(?:password|passwd|secret|token|api.?key)\s*[:=]\s*\S+"), "credential/secret"),
    (re.compile(r"(?i)\b(?:internal|confidential|under NDA|not for distribution)\b"), "confidentiality marker"),
    (re.compile(r"(?i)\$\s?\d[\d,.]*\s?(?:million|billion|M|B|k)\b"), "monetary amount"),
    (re.compile(r"(?i)\b\d+[\-\s]figure\b"), "monetary reference (N-figure)"),
    (re.compile(r"(?i)\b(?:revenue|budget|deal|contract|investment)\s+(?:of|worth|valued)\b"), "financial detail"),
]

EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"  # emoticons
    r"\U0001F300-\U0001F5FF"   # symbols and pictographs
    r"\U0001F680-\U0001F6FF"   # transport and map
    r"\U0001F1E0-\U0001F1FF"   # flags
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251"
    r"\U0001f900-\U0001f9FF"   # supplemental symbols
    r"\U00002600-\U000026FF"   # misc symbols
    r"]+",
    re.UNICODE,
)

EM_DASH_PATTERN = re.compile(r"[\u2014\u2013]")  # em dash and en dash


def sanitize_draft(text: str) -> str:
    """Auto-fix common LLM formatting issues before validation.

    Fixes mechanical issues that the LLM consistently generates
    despite prompt instructions. Logs when changes are made.
    """
    if not isinstance(text, str):
        return str(text) if text else ""
    original = text

    # Replace em/en dashes with commas
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)

    # Strip emoji characters
    text = EMOJI_PATTERN.sub("", text)

    # Ensure proper paragraph breaks for LinkedIn rendering
    # Add blank line before list items (handles both \n- and direct concatenation)
    text = re.sub(r"([^\n])\n(- )", r"\1\n\n\2", text)
    text = re.sub(r"([^\n\-])(- )", r"\1\n\n\2", text)
    # Add blank line between paragraphs (sentence end followed by new sentence)
    text = re.sub(r"([.!?])([A-Z])", r"\1\n\n\2", text)
    text = re.sub(r"([.!?])\n([A-Z])", r"\1\n\n\2", text)
    # Add blank line after colon-ending lines followed by list or paragraph
    text = re.sub(r"(:\n)(- )", r":\n\n\2", text)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim if over 1400 chars (cut at last sentence boundary)
    if len(text) > 1400:
        # Find last sentence end before 1400
        truncated = text[:1400]
        last_period = max(
            truncated.rfind(". "),
            truncated.rfind(".\n"),
            truncated.rfind("?\n"),
            truncated.rfind("? "),
        )
        if last_period > 800:
            text = text[: last_period + 1]
            # Re-append hashtags if they were cut
            hashtags = re.findall(r"#\w+", original)
            existing = re.findall(r"#\w+", text)
            if len(existing) < 3 and hashtags:
                text = text.rstrip() + "\n\n" + " ".join(hashtags[:5])

    if text != original:
        changes = []
        if "\u2014" in original or "\u2013" in original:
            changes.append("dashes")
        if EMOJI_PATTERN.search(original):
            changes.append("emoji")
        if len(original) > 1400 and len(text) <= 1400:
            changes.append(f"trimmed {len(original)}->{len(text)}")
        logger.info("Sanitized draft: %s", ", ".join(changes))

    return text.strip()

VALID_HASHTAGS = {
    "#Azure", "#LandingZones", "#CloudArchitecture", "#Terraform",
    "#InfrastructureAsCode", "#Kubernetes", "#AKS", "#GitHubCopilot",
    "#CloudSecurity", "#SovereignCloud", "#DevOps", "#OpenSource",
    "#AI", "#Microsoft", "#PlatformEngineering", "#CloudNative",
    "#CareerAdvice", "#MSP",
}


@dataclass
class ValidationResult:
    """Result of validating a draft post."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_draft(text: str, source_url: str = "", hashtags: list[str] | None = None) -> ValidationResult:
    """Validate a LinkedIn post draft against formatting rules.

    Checks:
    1. Character count: 800-1500 chars
    2. Hashtag count: 3-5
    3. Banned phrase scan
    4. Em/en dash check
    5. Emoji check
    6. Source link presence
    """
    if not isinstance(text, str):
        text = str(text) if text else ""
    result = ValidationResult()

    # 1. Character count
    char_count = len(text)
    if char_count < 800:
        result.add_error(f"Too short: {char_count} chars (minimum 800)")
    elif char_count > 1500:
        result.add_error(f"Too long: {char_count} chars (maximum 1500)")

    # 2. Hashtag count
    found_hashtags = re.findall(r"#\w+", text)
    if len(found_hashtags) < 3:
        result.add_error(f"Too few hashtags: {len(found_hashtags)} (minimum 3)")
    elif len(found_hashtags) > 5:
        result.add_error(f"Too many hashtags: {len(found_hashtags)} (maximum 5)")

    # Check hashtags are from the approved pool
    if hashtags:
        for ht in hashtags:
            if ht not in VALID_HASHTAGS:
                result.add_warning(f"Hashtag not in approved pool: {ht}")

    # 3. Banned phrase scan
    text_lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in text_lower:
            result.add_error(f"Contains banned phrase: '{phrase}'")

    # 4. Em/en dash check
    if EM_DASH_PATTERN.search(text):
        result.add_error("Contains em dash or en dash (use commas or periods instead)")

    # 5. Emoji check
    if EMOJI_PATTERN.search(text):
        result.add_error("Contains emoji characters")

    # 6. Customer name check (loaded from gitignored file)
    for name in _load_blocked_names():
        pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        if pattern.search(text):
            result.add_error(f"Contains blocked name: '{name}'")

    # 7. URL domain validation
    APPROVED_DOMAINS = {
        "azure.microsoft.com", "learn.microsoft.com", "devblogs.microsoft.com",
        "techcommunity.microsoft.com", "blog.aks.azure.com", "github.com",
        "kubernetes.io", "hashicorp.com", "aka.ms",
    }

    import urllib.parse
    urls_in_text = re.findall(r'https?://[^\s)>\]]+', text)
    for url in urls_in_text:
        domain = urllib.parse.urlparse(url).hostname or ""
        # Allow subdomains
        if not any(domain == d or domain.endswith("." + d) for d in APPROVED_DOMAINS):
            result.add_warning(f"URL from unapproved domain: {domain} ({url})")

    # 8. PII, credentials, monetary amounts, and confidential markers
    for pii_pattern, description in PII_PATTERNS:
        match = pii_pattern.search(text)
        if match:
            result.add_error(f"Contains {description}: '{match.group()}'")

    # 9. Source link
    if source_url and source_url not in text:
        result.add_warning("Source URL not found in post text")

    return result
