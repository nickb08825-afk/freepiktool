"""Tests for freepiktool.downloader (pure-logic helpers)."""

from __future__ import annotations

from freepiktool.downloader import _filename_from_headers, _cookies_from_requests_session


class TestFilenameFromHeaders:
    def test_content_disposition_quoted(self):
        headers = {"Content-Disposition": 'attachment; filename="sunset.jpg"'}
        assert _filename_from_headers(headers, "https://example.com/x") == "sunset.jpg"

    def test_content_disposition_unquoted(self):
        headers = {"Content-Disposition": "attachment; filename=photo.png"}
        assert _filename_from_headers(headers, "https://example.com/x") == "photo.png"

    def test_falls_back_to_url_path(self):
        headers = {}
        assert _filename_from_headers(headers, "https://example.com/images/cat.eps") == "cat.eps"

    def test_url_with_query_string(self):
        headers = {}
        name = _filename_from_headers(headers, "https://example.com/file.svg?token=abc")
        assert name == "file.svg"

    def test_no_info_returns_download(self):
        headers = {}
        name = _filename_from_headers(headers, "https://example.com/")
        assert name == "download"


class TestCookiesFromSession:
    def test_none_session_returns_empty(self):
        assert _cookies_from_requests_session(None) == {}

    def test_extracts_cookies(self):
        import requests

        s = requests.Session()
        s.cookies.set("session_id", "abc123", domain="freepik.com")
        cookies = _cookies_from_requests_session(s)
        assert cookies.get("session_id") == "abc123"
