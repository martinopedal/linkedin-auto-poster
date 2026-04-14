"""Tests for research tools."""

import unittest
from unittest.mock import MagicMock, patch

from src.feeds.research_tools import (
    _is_safe_url,
    check_terraform_resource,
    fetch_article,
    search_microsoft_learn,
)


class TestIsSafeUrl(unittest.TestCase):
    def test_https_allowed(self):
        assert _is_safe_url("https://azure.microsoft.com/updates") is True

    def test_http_blocked(self):
        assert _is_safe_url("http://azure.microsoft.com") is False

    def test_empty_blocked(self):
        assert _is_safe_url("") is False

    def test_localhost_blocked(self):
        assert _is_safe_url("https://localhost/secret") is False

    def test_private_ip_blocked(self):
        assert _is_safe_url("https://192.168.1.1/api") is False

    def test_link_local_blocked(self):
        assert _is_safe_url("https://169.254.169.254/metadata") is False


class TestFetchArticle(unittest.TestCase):
    def test_blocks_unsafe_url(self):
        result = fetch_article("http://evil.com")
        assert "Blocked" in result


class TestSearchLearn(unittest.TestCase):
    @patch("src.feeds.research_tools.requests.Session")
    def test_returns_results(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "results": [
                    {
                        "title": "AKS",
                        "description": "Azure K8s",
                        "url": "https://learn.microsoft.com/aks",
                    }
                ]
            },
        )
        result = search_microsoft_learn("AKS")
        assert "AKS" in result


class TestTerraformCheck(unittest.TestCase):
    @patch("src.feeds.research_tools.requests.Session")
    def test_provider_found(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_resp1 = MagicMock(status_code=200, json=lambda: {"version": "4.0"})
        mock_resp2 = MagicMock(status_code=200, text="azurerm_kubernetes_cluster resource docs")
        mock_session.get.side_effect = [mock_resp1, mock_resp2]
        result = check_terraform_resource("azurerm", "kubernetes_cluster")
        assert "Verified" in result
