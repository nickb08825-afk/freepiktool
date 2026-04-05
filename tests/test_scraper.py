"""Tests for freepiktool.scraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from freepiktool.scraper import (
    FormatLink,
    _normalise_fmt,
    _element_text,
    _resolve_url,
    scrape_format_links,
)


class TestNormaliseFmt:
    def test_jpg_extension_in_url(self):
        assert _normalise_fmt("Download", "https://dl.example.com/file.jpg") == "jpg"

    def test_jpeg_normalised_to_jpg(self):
        assert _normalise_fmt("Download", "https://dl.example.com/img.jpeg") == "jpg"

    def test_png_extension(self):
        assert _normalise_fmt("", "https://example.com/pic.png?foo=bar") == "png"

    def test_svg_extension(self):
        assert _normalise_fmt("SVG", "https://example.com/icon.svg") == "svg"

    def test_eps_extension(self):
        assert _normalise_fmt("EPS", "https://example.com/vec.eps") == "eps"

    def test_highres_keyword_in_text(self):
        assert _normalise_fmt("High Resolution download", "https://example.com/dl") == "highres"

    def test_hd_keyword(self):
        assert _normalise_fmt("Download HD", "https://example.com/dl") == "highres"

    def test_4k_keyword(self):
        assert _normalise_fmt("4K photo", "https://example.com/dl") == "highres"

    def test_jpg_in_label_no_extension(self):
        assert _normalise_fmt("JPG version", "https://example.com/dl") == "jpg"

    def test_unsupported_returns_none(self):
        assert _normalise_fmt("Download now", "https://example.com/file.pdf") is None


class TestResolveUrl:
    def test_absolute_url_unchanged(self):
        url = "https://cdn.freepik.com/file.zip"
        assert _resolve_url(url) == url

    def test_relative_url_resolved(self):
        result = _resolve_url("/download/123")
        assert result == "https://www.freepik.com/download/123"


class TestScrapeFormatLinks:
    def _make_session(self, html: str, status: int = 200) -> requests.Session:
        session = MagicMock(spec=requests.Session)
        resp = MagicMock()
        resp.status_code = status
        resp.text = html
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp
        # HEAD for redirect resolution → return same URL
        session.head.side_effect = requests.RequestException("no HEAD")
        return session

    def test_finds_jpg_link(self):
        html = """
        <html><body>
          <a href="https://dl.freepik.com/photo.jpg" class="download-button">JPG</a>
        </body></html>
        """
        session = self._make_session(html)
        with patch("freepiktool.scraper._follow_redirect", side_effect=lambda s, u, **kw: u):
            links = scrape_format_links("https://www.freepik.com/resource/1", session)

        fmts = {lnk.fmt for lnk in links}
        assert "jpg" in fmts

    def test_finds_png_svg_eps(self):
        html = """
        <html><body>
          <a href="https://dl.freepik.com/img.png" data-download="1">PNG</a>
          <a href="https://dl.freepik.com/vec.svg" data-download="1">SVG</a>
          <a href="https://dl.freepik.com/vec.eps" data-download="1">EPS</a>
        </body></html>
        """
        session = self._make_session(html)
        with patch("freepiktool.scraper._follow_redirect", side_effect=lambda s, u, **kw: u):
            links = scrape_format_links("https://www.freepik.com/resource/2", session)

        fmts = {lnk.fmt for lnk in links}
        assert {"png", "svg", "eps"}.issubset(fmts)

    def test_finds_highres_by_label(self):
        html = """
        <html><body>
          <a href="https://dl.freepik.com/download/hd" class="download-button">
            High Resolution
          </a>
        </body></html>
        """
        session = self._make_session(html)
        with patch("freepiktool.scraper._follow_redirect", side_effect=lambda s, u, **kw: u):
            links = scrape_format_links("https://www.freepik.com/resource/3", session)

        fmts = {lnk.fmt for lnk in links}
        assert "highres" in fmts

    def test_deduplicates_by_url(self):
        html = """
        <html><body>
          <a href="https://dl.freepik.com/photo.jpg" data-download="1">JPG</a>
          <a href="https://dl.freepik.com/photo.jpg" class="download-button">Download JPG</a>
        </body></html>
        """
        session = self._make_session(html)
        with patch("freepiktool.scraper._follow_redirect", side_effect=lambda s, u, **kw: u):
            links = scrape_format_links("https://www.freepik.com/resource/4", session)

        urls = [lnk.url for lnk in links]
        assert len(urls) == len(set(urls))

    def test_request_error_returns_empty(self):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.RequestException("timeout")
        links = scrape_format_links("https://www.freepik.com/resource/5", session)
        assert links == []

    def test_ignores_unsupported_formats(self):
        html = """
        <html><body>
          <a href="https://dl.freepik.com/file.pdf" data-download="1">PDF</a>
          <a href="https://dl.freepik.com/file.zip" data-download="1">ZIP</a>
        </body></html>
        """
        session = self._make_session(html)
        with patch("freepiktool.scraper._follow_redirect", side_effect=lambda s, u, **kw: u):
            links = scrape_format_links("https://www.freepik.com/resource/6", session)
        assert links == []
