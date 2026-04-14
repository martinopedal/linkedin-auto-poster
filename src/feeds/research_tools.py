"""Research tools for grounding LinkedIn posts in verified sources."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)


def _is_safe_url(url: str) -> bool:
    """Validate URL is safe to fetch (SSRF protection)."""
    if not url.startswith("https://"):
        return False
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False
    # Block private/local IPs with bounded DNS resolution
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(socket.getaddrinfo, hostname, None)
            try:
                ips = future.result(timeout=5)
            except concurrent.futures.TimeoutError:
                logger.warning("DNS resolution timed out for %s", hostname)
                return False
        for _, _, _, _, sockaddr in ips:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                logger.warning("Blocked private IP for %s: %s", hostname, ip)
                return False
    except (socket.gaierror, OSError, UnicodeError) as e:
        logger.warning("DNS resolution failed for %s: %s", hostname, e)
        return False
    return True


def fetch_article(url: str, max_length: int = 2000) -> str:
    """Fetch article content from a URL. SSRF-protected."""
    if not _is_safe_url(url):
        return f"Blocked: unsafe URL {url}"

    with requests.Session() as session:
        retries = Retry(total=1, backoff_factor=1, status_forcelist=[500, 502, 503])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        try:
            resp = session.get(
                url, timeout=15,
                headers={"User-Agent": "linkedin-auto-poster/1.0"},
                allow_redirects=False,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            return f"Fetch failed: {e}"

    # Strip HTML
    text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]


def search_microsoft_learn(query: str, max_results: int = 3) -> str:
    """Search Microsoft Learn for documentation. Returns top results."""
    url = "https://learn.microsoft.com/api/search"
    params = {"search": query, "locale": "en-us", "$top": max_results}
    with requests.Session() as session:
        retries = Retry(total=1, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        try:
            resp = session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return "Unexpected Learn API response format"
            results = data.get("results", [])
            if not isinstance(results, list):
                return "Unexpected Learn API results format"
            if not results:
                return f"No Microsoft Learn results for: {query}"
            output = []
            for r in results[:max_results]:
                title = r.get("title", "")
                snippet = r.get("description", "")[:200]
                doc_url = r.get("url", "")
                output.append(f"- {title}: {snippet} ({doc_url})")
            return "\n".join(output)
        except Exception as e:
            return f"Learn search failed: {e}"


def check_terraform_resource(provider: str, resource_type: str) -> str:
    """Check if a Terraform resource type exists in the registry."""
    url = f"https://registry.terraform.io/v1/providers/hashicorp/{provider}"
    with requests.Session() as session:
        retries = Retry(total=1, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 404:
                return f"Provider {provider} not found in Terraform Registry"
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return "Unexpected Terraform registry response"
            version = data.get("version", "unknown")
            # Stronger verification: check docs page contains the resource name
            docs_url = (
                f"https://registry.terraform.io/providers/hashicorp/{provider}"
                f"/latest/docs/resources/{resource_type}"
            )
            docs_resp = session.get(docs_url, timeout=10, allow_redirects=True)
            if docs_resp.status_code == 200 and resource_type in docs_resp.text.lower():
                return f"Verified: {provider}/{resource_type} exists (provider v{version})"
            return f"Provider {provider} v{version} found but resource {resource_type} not verified"
        except Exception as e:
            return f"Terraform check failed: {e}"
