"""Tests for freepiktool.zipper."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from freepiktool.zipper import _safe_name, zip_results


class TestSafeName:
    def test_plain_query(self):
        assert _safe_name("cats") == "cats"

    def test_spaces_become_underscores(self):
        assert _safe_name("cute cats") == "cute_cats"

    def test_special_chars_removed(self):
        assert _safe_name("cute cats!") == "cute_cats"

    def test_leading_trailing_stripped(self):
        assert _safe_name("  hello  ") == "hello"

    def test_empty_string_fallback(self):
        assert _safe_name("!!!") == "download"

    def test_multiple_spaces_collapsed(self):
        assert _safe_name("a  b   c") == "a_b_c"


class TestZipResults:
    def test_creates_archive(self, tmp_path):
        f1 = tmp_path / "a.jpg"
        f2 = tmp_path / "b.png"
        f1.write_bytes(b"jpeg-data")
        f2.write_bytes(b"png-data")

        archive = zip_results([f1, f2], query="cats", dest_dir=tmp_path)

        assert archive.name == "cats.zip"
        assert archive.exists()
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
        assert "a.jpg" in names
        assert "b.png" in names

    def test_archive_named_after_query(self, tmp_path):
        f = tmp_path / "file.svg"
        f.write_bytes(b"<svg/>")

        archive = zip_results([f], query="sunset landscape", dest_dir=tmp_path)
        assert archive.name == "sunset_landscape.zip"

    def test_no_overwrite_existing_archive(self, tmp_path):
        f = tmp_path / "img.eps"
        f.write_bytes(b"%!PS")

        # Create first archive.
        a1 = zip_results([f], query="test", dest_dir=tmp_path)
        # Write the file again (zip_results deleted original; recreate).
        f.write_bytes(b"%!PS")
        a2 = zip_results([f], query="test", dest_dir=tmp_path)

        assert a1 != a2
        assert a1.exists()
        assert a2.exists()

    def test_remove_originals(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")

        zip_results([f], query="photo", dest_dir=tmp_path, remove_originals=True)
        assert not f.exists()

    def test_keep_originals(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")

        zip_results([f], query="photo", dest_dir=tmp_path, remove_originals=False)
        assert f.exists()

    def test_empty_paths_raises(self, tmp_path):
        with pytest.raises(ValueError):
            zip_results([], query="test", dest_dir=tmp_path)

    def test_missing_file_skipped(self, tmp_path):
        present = tmp_path / "real.png"
        present.write_bytes(b"data")
        ghost = tmp_path / "ghost.png"

        archive = zip_results([present, ghost], query="mix", dest_dir=tmp_path)
        with zipfile.ZipFile(archive) as zf:
            assert "real.png" in zf.namelist()
            assert "ghost.png" not in zf.namelist()
