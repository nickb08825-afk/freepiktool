"""Tests for freepiktool.search (data-model helpers, no network)."""

from __future__ import annotations

from freepiktool.search import Resource, _parse_resource


class TestResource:
    def _make(self, **kwargs):
        defaults = dict(
            id=1,
            title="Test",
            url="https://www.freepik.com/resource/1",
            download_url="https://dl.freepik.com/file.jpg",
            license="free",
        )
        defaults.update(kwargs)
        return Resource(**defaults)

    def test_all_download_urls_primary_only(self):
        r = self._make()
        assert r.all_download_urls() == ["https://dl.freepik.com/file.jpg"]

    def test_all_download_urls_includes_formats(self):
        r = self._make()
        r.format_urls = {
            "png": ["https://dl.freepik.com/file.png"],
            "svg": ["https://dl.freepik.com/file.svg"],
        }
        urls = r.all_download_urls()
        assert "https://dl.freepik.com/file.jpg" in urls
        assert "https://dl.freepik.com/file.png" in urls
        assert "https://dl.freepik.com/file.svg" in urls

    def test_all_download_urls_deduplicates(self):
        r = self._make()
        r.format_urls = {
            "jpg": ["https://dl.freepik.com/file.jpg"],  # same as primary
        }
        urls = r.all_download_urls()
        assert urls.count("https://dl.freepik.com/file.jpg") == 1


class TestParseResource:
    def test_parses_basic_resource(self):
        raw = {
            "id": 42,
            "title": "Cat photo",
            "url": "https://www.freepik.com/resource/42",
            "download": {"url": "https://dl.freepik.com/cat.jpg"},
            "type": "photo",
        }
        r = _parse_resource(raw, "free", False)
        assert r is not None
        assert r.id == 42
        assert r.title == "Cat photo"
        assert r.download_url == "https://dl.freepik.com/cat.jpg"
        assert r.license == "free"
        assert r.is_ai_generated is False

    def test_parses_ai_resource(self):
        raw = {"id": 99, "title": "AI art", "url": "https://www.freepik.com/resource/99"}
        r = _parse_resource(raw, "premium", True)
        assert r is not None
        assert r.is_ai_generated is True
        assert r.license == "premium"

    def test_missing_id_returns_none(self):
        assert _parse_resource({}, "free", False) is None

    def test_fallback_download_url_field(self):
        raw = {
            "id": 7,
            "title": "Vector",
            "url": "https://www.freepik.com/resource/7",
            "download_url": "https://dl.freepik.com/vec.eps",
        }
        r = _parse_resource(raw, "free", False)
        assert r is not None
        assert r.download_url == "https://dl.freepik.com/vec.eps"
