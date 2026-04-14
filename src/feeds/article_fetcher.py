"""Fetch and extract text from source article URLs for grounding."""

from __future__ import annotations

import logging
import re

import requests
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)

# Max chars of article text to include in LLM context
MAX_ARTICLE_LENGTH = 2000


def fetch_article_text(url: str, timeout: int = 15) -> str | None:
    """Fetch a URL and extract readable text content.

    Returns cleaned text up to MAX_ARTICLE_LENGTH chars,
    or None if fetch fails.
    """
    if not url or not url.startswith("https://"):
        return None

    with requests.Session() as session:
        retries = Retry(total=1, backoff_factor=1, status_forcelist=[500, 502, 503])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        try:
            resp = session.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "linkedin-auto-poster/1.0"},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to fetch article %s: %s", url, e)
            return None

    return _extract_text(resp.text)


def _extract_text(html: str) -> str:
    """Extract readable text from HTML, removing tags and scripts."""
    # Remove script/style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Truncate
    if len(text) > MAX_ARTICLE_LENGTH:
        # Cut at last sentence boundary
        truncated = text[:MAX_ARTICLE_LENGTH]
        last_period = max(truncated.rfind(". "), truncated.rfind(".\n"))
        if last_period > MAX_ARTICLE_LENGTH // 2:
            text = text[:last_period + 1]
        else:
            text = truncated
    return text
