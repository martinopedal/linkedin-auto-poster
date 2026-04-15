"""Tests for LinkedIn API client (mocked HTTP)."""

import responses

from src.linkedin.client import LinkedInAuthError, LinkedInClient


class TestLinkedInClient:
    def _make_client(self) -> LinkedInClient:
        return LinkedInClient(
            client_id="test-id",
            client_secret="test-secret",
            refresh_token="test-refresh-token",
        )

    @responses.activate
    def test_refresh_access_token(self):
        responses.add(
            responses.POST,
            "https://www.linkedin.com/oauth/v2/accessToken",
            json={"access_token": "new-access-token", "expires_in": 5184000},
            status=200,
        )
        client = self._make_client()
        token = client.refresh_access_token()
        assert token == "new-access-token"
        assert client.access_token == "new-access-token"

    @responses.activate
    def test_refresh_with_new_refresh_token(self):
        responses.add(
            responses.POST,
            "https://www.linkedin.com/oauth/v2/accessToken",
            json={"access_token": "at", "refresh_token": "new-rt", "expires_in": 5184000},
            status=200,
        )
        client = self._make_client()
        client.refresh_access_token()
        assert client.refresh_token == "new-rt"

    @responses.activate
    def test_refresh_failure_raises(self):
        responses.add(
            responses.POST,
            "https://www.linkedin.com/oauth/v2/accessToken",
            json={"error": "invalid_grant"},
            status=400,
        )
        client = self._make_client()
        try:
            client.refresh_access_token()
            assert False, "Should have raised"
        except LinkedInAuthError:
            pass

    @responses.activate
    def test_get_person_urn(self):
        responses.add(
            responses.GET,
            "https://api.linkedin.com/v2/userinfo",
            json={"sub": "abc123"},
            status=200,
        )
        client = self._make_client()
        client.access_token = "valid-token"
        urn = client.get_person_urn()
        assert urn == "urn:li:person:abc123"

    @responses.activate
    def test_create_post_dry_run(self):
        responses.add(
            responses.GET,
            "https://api.linkedin.com/v2/userinfo",
            json={"sub": "abc123"},
            status=200,
        )
        client = self._make_client()
        client.access_token = "valid-token"
        result = client.create_post("Test post", dry_run=True)
        assert result is None

    @responses.activate
    def test_create_post_success(self):
        responses.add(
            responses.GET,
            "https://api.linkedin.com/v2/userinfo",
            json={"sub": "abc123"},
            status=200,
        )
        responses.add(
            responses.POST,
            "https://api.linkedin.com/v2/ugcPosts",
            status=201,
            headers={"x-restli-id": "urn:li:share:123456"},
        )
        client = self._make_client()
        client.access_token = "valid-token"
        urn = client.create_post("Test post content")
        assert urn == "urn:li:share:123456"

    @responses.activate
    def test_retry_on_401_then_success(self):
        responses.add(
            responses.GET,
            "https://api.linkedin.com/v2/userinfo",
            json={"sub": "abc123"},
            status=200,
        )
        # First post attempt returns 401
        responses.add(
            responses.POST,
            "https://api.linkedin.com/v2/ugcPosts",
            status=401,
        )
        # Token refresh succeeds
        responses.add(
            responses.POST,
            "https://www.linkedin.com/oauth/v2/accessToken",
            json={"access_token": "fresh-token", "expires_in": 5184000},
            status=200,
        )
        # Second post attempt succeeds
        responses.add(
            responses.POST,
            "https://api.linkedin.com/v2/ugcPosts",
            status=201,
            headers={"x-restli-id": "urn:li:share:789"},
        )
        client = self._make_client()
        client.access_token = "expired-token"
        urn = client.create_post("Test post")
        assert urn == "urn:li:share:789"

    def test_no_refresh_token_raises(self):
        client = LinkedInClient(client_id="id", client_secret="secret", refresh_token="")
        try:
            client.refresh_access_token()
            assert False, "Should have raised"
        except LinkedInAuthError:
            pass

    @responses.activate
    def test_create_post_with_article(self):
        responses.add(
            responses.GET,
            "https://api.linkedin.com/v2/userinfo",
            json={"sub": "abc123"},
            status=200,
        )
        responses.add(
            responses.POST,
            "https://api.linkedin.com/v2/ugcPosts",
            status=201,
            headers={"x-restli-id": "urn:li:share:article1"},
        )
        client = self._make_client()
        client.access_token = "valid-token"
        urn = client.create_post(
            "Check out this update",
            article_url="https://example.com/article",
            article_title="Example Article",
        )
        assert urn == "urn:li:share:article1"
