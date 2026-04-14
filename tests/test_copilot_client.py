"""Tests for Copilot client helpers."""

import json
import unittest

from src.drafts.copilot_client import _is_retryable_error
from src.drafts.drafter import _parse_llm_json


class TestIsRetryableError(unittest.TestCase):
    def test_timeout_is_retryable(self):
        assert _is_retryable_error(Exception("Request timeout after 30s"))

    def test_429_is_retryable(self):
        assert _is_retryable_error(Exception("HTTP 429 Too Many Requests"))

    def test_500_is_retryable(self):
        assert _is_retryable_error(Exception("Internal Server Error 500"))

    def test_502_is_retryable(self):
        assert _is_retryable_error(Exception("502 Bad Gateway"))

    def test_503_is_retryable(self):
        assert _is_retryable_error(Exception("503 Service Unavailable"))

    def test_504_is_retryable(self):
        assert _is_retryable_error(Exception("504 Gateway Timeout"))

    def test_connection_error_is_retryable(self):
        assert _is_retryable_error(Exception("Connection refused"))

    def test_eof_is_retryable(self):
        assert _is_retryable_error(Exception("Unexpected EOF in stream"))

    def test_400_not_retryable(self):
        assert not _is_retryable_error(Exception("HTTP 400 Bad Request"))

    def test_auth_error_not_retryable(self):
        assert not _is_retryable_error(Exception("401 Unauthorized"))

    def test_generic_error_not_retryable(self):
        assert not _is_retryable_error(Exception("Something went wrong"))

    def test_case_insensitive(self):
        assert _is_retryable_error(Exception("TIMEOUT waiting for response"))


class TestParseLlmJson(unittest.TestCase):
    def test_raw_json(self):
        raw = '{"title": "Hello", "body": "World"}'
        result = _parse_llm_json(raw)
        assert result == {"title": "Hello", "body": "World"}

    def test_markdown_fenced_json(self):
        raw = 'Here is the output:\n```json\n{"title": "Hello"}\n```\n'
        result = _parse_llm_json(raw)
        assert result == {"title": "Hello"}

    def test_preamble_before_json(self):
        raw = "Sure, here is the JSON:\n{\"key\": \"value\"}"
        result = _parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_postamble_after_json(self):
        raw = '{"key": "value"}\nLet me know if you need changes.'
        result = _parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_no_valid_json_raises(self):
        with self.assertRaises((json.JSONDecodeError, ValueError)):
            _parse_llm_json("This is just plain text with no JSON at all")

    def test_empty_string_raises(self):
        with self.assertRaises((json.JSONDecodeError, ValueError)):
            _parse_llm_json("")

    def test_nested_json(self):
        raw = '{"outer": {"inner": [1, 2, 3]}}'
        result = _parse_llm_json(raw)
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_whitespace_padded(self):
        raw = "   \n  {\"a\": 1}  \n  "
        result = _parse_llm_json(raw)
        assert result == {"a": 1}
