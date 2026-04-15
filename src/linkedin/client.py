"""LinkedIn API client: OAuth token management and post publishing."""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"
LINKEDIN_API_VERSION = "202603"


class LinkedInClient:
    """LinkedIn API client with OAuth token management."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        access_token: str | None = None,
    ):
        self.client_id = client_id or os.environ.get("LINKEDIN_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("LINKEDIN_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or os.environ.get("LINKEDIN_REFRESH_TOKEN", "")
        self.access_token = access_token or os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
        self.person_urn: str | None = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Linkedin-Version": LINKEDIN_API_VERSION,
            "Content-Type": "application/json",
        }

    def ensure_access_token(self) -> str:
        """Get a valid access token, refreshing if possible."""
        if self.access_token:
            try:
                self.get_person_urn()
                return self.access_token
            except LinkedInAuthError:
                if self.refresh_token:
                    logger.info("Access token expired, refreshing...")
                    return self.refresh_access_token()
                raise LinkedInAuthError(
                    "Access token expired and no refresh token available. "
                    "Re-run scripts/linkedin_setup.py and update the LINKEDIN_ACCESS_TOKEN secret."
                )

        if self.refresh_token:
            return self.refresh_access_token()

        raise LinkedInAuthError(
            "No access token or refresh token available. "
            "Run scripts/linkedin_setup.py and set LINKEDIN_ACCESS_TOKEN as a GitHub Secret."
        )

    def refresh_access_token(self) -> str:
        """Exchange refresh token for a new access token."""
        if not self.refresh_token:
            raise LinkedInAuthError("No refresh token available. Run scripts/linkedin_setup.py first.")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        resp = requests.post(LINKEDIN_TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise LinkedInAuthError(f"Token refresh failed ({resp.status_code}): {resp.text}")

        body = resp.json()
        self.access_token = body["access_token"]
        if "refresh_token" in body:
            self.refresh_token = body["refresh_token"]
            logger.info("Received new refresh token")

        logger.info("Access token refreshed successfully")
        return self.access_token

    def get_person_urn(self) -> str:
        """Get the authenticated member's person URN."""
        if self.person_urn:
            return self.person_urn

        resp = requests.get(
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30,
        )
        if resp.status_code == 401:
            raise LinkedInAuthError("Access token is invalid or expired")
        resp.raise_for_status()

        sub = resp.json().get("sub", "")
        self.person_urn = f"urn:li:person:{sub}"
        logger.info("Authenticated as %s", self.person_urn)
        return self.person_urn

    def create_post(
        self,
        text: str,
        article_url: str | None = None,
        article_title: str | None = None,
        visibility: str = "PUBLIC",
        dry_run: bool = False,
    ) -> str | None:
        """Create a LinkedIn post. Returns the post URN on success.

        Args:
            text: Post body text.
            article_url: Optional URL to attach as an article preview.
            article_title: Optional title for the article.
            visibility: PUBLIC or CONNECTIONS.
            dry_run: If True, validate but do not post.

        Returns:
            LinkedIn post URN string, or None on dry run.
        """
        self.ensure_access_token()
        person_urn = self.get_person_urn()

        # Build UGC post payload (Share on LinkedIn product uses /v2/ugcPosts)
        share_content: dict = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE",
        }

        if article_url:
            share_content["shareMediaCategory"] = "ARTICLE"
            share_content["media"] = [{
                "status": "READY",
                "originalUrl": article_url,
                "title": {"text": article_title or ""},
            }]

        payload: dict = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": share_content,
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility,
            },
        }

        if dry_run:
            logger.info("DRY RUN: would post %d chars to LinkedIn", len(text))
            return None

        resp = self._post_with_retry(LINKEDIN_POSTS_URL, payload)
        post_urn = resp.headers.get("x-restli-id", "")
        logger.info("Published post: %s", post_urn)
        return post_urn

    def _post_with_retry(self, url: str, payload: dict, retries: int = 2) -> requests.Response:
        """POST with retry on 429/5xx."""
        for attempt in range(retries + 1):
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)

            if resp.status_code == 201:
                return resp
            if resp.status_code == 401:
                if attempt == 0 and self.refresh_token:
                    logger.warning("401 on post, refreshing token...")
                    self.refresh_access_token()
                    continue
                raise LinkedInAuthError(
                    f"Auth failed ({resp.status_code}). Token may be expired. "
                    "Re-run scripts/linkedin_setup.py and update LINKEDIN_ACCESS_TOKEN."
                )
            if resp.status_code == 429:
                try:
                    wait = int(resp.headers.get("Retry-After", 60))
                except (ValueError, TypeError):
                    wait = 60
                logger.warning("Rate limited, waiting %ds...", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                logger.warning("Server error %d, retrying...", resp.status_code)
                time.sleep(5 * (attempt + 1))
                continue

            resp.raise_for_status()

        raise LinkedInAPIError(f"Failed after {retries + 1} attempts: {resp.status_code} {resp.text}")


class LinkedInAuthError(Exception):
    """Raised when LinkedIn authentication fails."""


class LinkedInAPIError(Exception):
    """Raised when a LinkedIn API call fails."""
