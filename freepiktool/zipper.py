"""Package all downloaded files into a zip archive named after the search query.

The zip file is placed in *dest_dir* and named ``<safe_query>.zip`` where
``<safe_query>`` is the search query with characters that are unsafe in
filenames replaced by underscores.

Example::

    paths = download(urls, dest_dir="/tmp/cats")
    archive = zip_results(paths, query="cute cats", dest_dir="/tmp/cats")
    # → /tmp/cats/cute_cats.zip
"""

from __future__ import annotations

import logging
import os
import re
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Characters that are unsafe (or awkward) in filenames on common OS platforms.
_UNSAFE_CHARS_RE = re.compile(r'[^\w\-.]')


def _safe_name(query: str) -> str:
    """Convert *query* into a filesystem-safe string for the zip filename.

    Runs of unsafe characters are collapsed to a single underscore and
    leading/trailing underscores are stripped.

    >>> _safe_name("cute cats!")
    'cute_cats'
    >>> _safe_name("  Hello, World!  ")
    'Hello_World'
    """
    safe = _UNSAFE_CHARS_RE.sub("_", query.strip())
    # Collapse multiple consecutive underscores.
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("_") or "download"


def zip_results(
    paths: list[Path],
    query: str,
    dest_dir: str | os.PathLike = ".",
    *,
    remove_originals: bool = False,
) -> Path:
    """Zip *paths* into ``<dest_dir>/<safe_query>.zip``.

    Args:
        paths: Files to include in the archive.
        query: The search query used to name the zip file.
        dest_dir: Directory in which to write the zip archive.
        remove_originals: When *True*, delete the individual files after they
            have been added to the archive successfully.

    Returns:
        :class:`pathlib.Path` of the created zip archive.

    Raises:
        ValueError: if *paths* is empty.
    """
    if not paths:
        raise ValueError("No files to zip.")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    archive_name = f"{_safe_name(query)}.zip"
    archive_path = dest / archive_name

    # If the archive already exists, use a numbered suffix to avoid overwriting.
    if archive_path.exists():
        stem = archive_path.stem
        counter = 1
        while archive_path.exists():
            archive_path = dest / f"{stem}_{counter}.zip"
            counter += 1

    logger.info("Creating archive %s with %d file(s) …", archive_path, len(paths))

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in paths:
            file_path = Path(file_path)
            if not file_path.is_file():
                logger.warning("Skipping missing file: %s", file_path)
                continue
            # Store files at the top level of the archive (no sub-directories).
            zf.write(file_path, arcname=file_path.name)
            logger.debug("Added %s → %s", file_path, archive_name)

    logger.info("Archive created: %s", archive_path)

    if remove_originals:
        for file_path in paths:
            file_path = Path(file_path)
            if file_path.is_file():
                try:
                    file_path.unlink()
                    logger.debug("Removed original: %s", file_path)
                except OSError as exc:
                    logger.warning("Could not remove %s: %s", file_path, exc)

    return archive_path
