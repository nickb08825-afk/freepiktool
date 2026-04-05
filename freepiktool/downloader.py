"""Concurrent, resilient downloader for Freepik assets.

Key features
------------
* **Async I/O** – uses *aiohttp* + *asyncio* so multiple downloads run in
  parallel without spawning threads.
* **Configurable concurrency** – a semaphore caps the number of simultaneous
  connections (default 5).
* **Automatic retry** – transient network errors and 5xx responses are retried
  with exponential back-off.
* **Progress reporting** – a *tqdm* progress bar shows bytes received for each
  download.
* **Smart filename detection** – tries the ``Content-Disposition`` header
  before falling back to the URL path.
* **Session cookie bridging** – accepts an authenticated
  :class:`requests.Session` and forwards its cookies to *aiohttp*.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

import aiofiles
import aiohttp
from tqdm import tqdm

logger = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = 5
_DEFAULT_RETRIES = 3
_DEFAULT_CHUNK_SIZE = 1024 * 64  # 64 KiB

# Regex to extract filename from Content-Disposition header.
_CD_FILENAME_RE = re.compile(
    r'filename[^;=\n]*=\s*(?:["\']?)(?P<name>[^;\n"\']+)', re.IGNORECASE
)


def _filename_from_headers(headers: dict, url: str) -> str:
    """Derive a local filename from response headers or the URL."""
    cd = headers.get("Content-Disposition", "")
    match = _CD_FILENAME_RE.search(cd)
    if match:
        return match.group("name").strip()
    # Fall back to the last segment of the URL path.
    path = urlparse(url).path
    name = unquote(path.split("/")[-1]) or "download"
    return name


def _cookies_from_requests_session(session) -> dict[str, str]:
    """Extract cookies from a :class:`requests.Session` as a plain dict."""
    if session is None:
        return {}
    return dict(session.cookies)


async def _download_one(
    sem: asyncio.Semaphore,
    aio_session: aiohttp.ClientSession,
    url: str,
    dest_dir: Path,
    retries: int,
    chunk_size: int,
) -> Path:
    """Download *url* into *dest_dir*, returning the path of the saved file."""
    attempt = 0
    delay = 1.0

    while True:
        attempt += 1
        try:
            async with sem:
                async with aio_session.get(url, allow_redirects=True) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", delay))
                        logger.warning("Rate-limited. Waiting %ss …", retry_after)
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()

                    filename = _filename_from_headers(dict(resp.headers), url)
                    dest_path = dest_dir / filename
                    # Avoid overwriting: append a counter suffix if needed.
                    if dest_path.exists():
                        stem, suffix = dest_path.stem, dest_path.suffix
                        counter = 1
                        while dest_path.exists():
                            dest_path = dest_dir / f"{stem}_{counter}{suffix}"
                            counter += 1

                    total = int(resp.headers.get("Content-Length", 0)) or None

                    with tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=filename,
                        leave=False,
                    ) as bar:
                        async with aiofiles.open(dest_path, "wb") as fh:
                            async for chunk in resp.content.iter_chunked(chunk_size):
                                await fh.write(chunk)
                                bar.update(len(chunk))

                    logger.info("Saved → %s", dest_path)
                    return dest_path

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            if attempt > retries:
                logger.error("Failed to download %s after %d attempts: %s", url, retries, exc)
                raise
            logger.warning(
                "Download attempt %d/%d failed for %s (%s). Retrying in %.1fs …",
                attempt,
                retries,
                url,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def _download_all(
    urls: list[str],
    dest_dir: Path,
    cookies: dict[str, str],
    concurrency: int,
    retries: int,
    chunk_size: int,
    timeout_secs: int,
) -> list[Path]:
    """Run all downloads concurrently and return saved paths."""
    sem = asyncio.Semaphore(concurrency)
    timeout = aiohttp.ClientTimeout(total=timeout_secs)
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
        ),
        "Referer": "https://www.freepik.com/",
    }

    async with aiohttp.ClientSession(
        cookies=cookies,
        headers=headers,
        timeout=timeout,
        connector=connector,
    ) as aio_session:
        tasks = [
            _download_one(sem, aio_session, url, dest_dir, retries, chunk_size)
            for url in urls
        ]

        results: list[Path] = []
        with tqdm(total=len(tasks), desc="Overall progress", unit="file") as overall_bar:
            for coro in asyncio.as_completed(tasks):
                try:
                    path = await coro
                    results.append(path)
                except Exception as exc:
                    logger.error("A download failed: %s", exc)
                finally:
                    overall_bar.update(1)

    return results


def download(
    urls: Iterable[str],
    dest_dir: str | os.PathLike = ".",
    *,
    session=None,
    concurrency: int = _DEFAULT_CONCURRENCY,
    retries: int = _DEFAULT_RETRIES,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    timeout_secs: int = 120,
) -> list[Path]:
    """Download *urls* concurrently and save them to *dest_dir*.

    Args:
        urls: Iterable of direct download URLs.
        dest_dir: Directory in which to save downloaded files.
        session: Optional authenticated :class:`requests.Session` whose
            cookies will be forwarded to every download request.
        concurrency: Maximum simultaneous connections.
        retries: Per-URL retry count on transient errors.
        chunk_size: Bytes per read chunk.
        timeout_secs: Total request timeout in seconds.

    Returns:
        List of :class:`pathlib.Path` objects for successfully saved files.
    """
    url_list = list(urls)
    if not url_list:
        return []

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    cookies = _cookies_from_requests_session(session)

    logger.info(
        "Downloading %d file(s) → %s  [concurrency=%d, retries=%d]",
        len(url_list),
        dest,
        concurrency,
        retries,
    )

    return asyncio.run(
        _download_all(
            url_list,
            dest,
            cookies,
            concurrency,
            retries,
            chunk_size,
            timeout_secs,
        )
    )
