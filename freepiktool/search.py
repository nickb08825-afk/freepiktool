"""Freepik API search.

Searches the Freepik REST API for assets matching a query and returns
download URLs covering **all three tiers**:

* **Basic / free** resources (``license=free``)
* **Premium** resources (``license=premium``)
* **AI-generated artwork** (``content_type[ai][generated]=1``)

All tiers are fetched concurrently; every available page is walked
automatically so no results are silently dropped.

API authentication
------------------
A Freepik API key is required.  Supply it via the ``FREEPIK_API_KEY``
environment variable or the *.env* file (loaded automatically).

Reference: https://docs.freepik.com/reference/resources-list
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Iterator

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_API_BASE = "https://api.freepik.com/v1"
_RESOURCES_URL = f"{_API_BASE}/resources"
_DOWNLOAD_URL = f"{_API_BASE}/resources/{{resource_id}}/download"

# Maximum results per page allowed by the API.
_PAGE_LIMIT = 100


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Resource:
    """A single Freepik search result."""

    id: int
    title: str
    url: str                          # Freepik detail-page URL
    download_url: str                 # Direct download URL
    license: str                      # "free" | "premium"
    is_ai_generated: bool = False
    content_type: str = ""
    extra: dict = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover
        tag = "[AI]" if self.is_ai_generated else f"[{self.license}]"
        return f"{tag} {self.title!r} → {self.download_url}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_api_key(api_key: str | None) -> str:
    key = api_key or os.getenv("FREEPIK_API_KEY")
    if not key:
        raise ValueError(
            "Freepik API key not found. "
            "Set FREEPIK_API_KEY in your environment or pass --api-key."
        )
    return key


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "x-freepik-api-key": api_key,
        "Accept-Language": "en-US",
        "Accept": "application/json",
    }


def _fetch_download_url(
    session: requests.Session,
    resource_id: int,
    api_key: str,
) -> str:
    """Resolve the direct download URL for *resource_id* via the API."""
    url = _DOWNLOAD_URL.format(resource_id=resource_id)
    resp = session.get(url, headers=_build_headers(api_key), timeout=30)
    if resp.status_code == 403:
        # Premium resource and account tier doesn't allow it — skip gracefully.
        logger.debug("No download access for resource %s (403).", resource_id)
        return ""
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", {}).get("url", "")


def _parse_resource(raw: dict, license_value: str, is_ai: bool) -> Resource | None:
    """Convert a raw API dict into a :class:`Resource`, or *None* to skip."""
    resource_id = raw.get("id")
    if not resource_id:
        return None

    # The download URL may already be included in the search payload, or we
    # may need to fetch it separately; we defer that to the caller.
    download_url = (
        raw.get("download", {}).get("url", "")
        or raw.get("download_url", "")
    )

    return Resource(
        id=int(resource_id),
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        download_url=download_url,
        license=license_value,
        is_ai_generated=is_ai,
        content_type=raw.get("type", ""),
        extra=raw,
    )


def _iter_pages(
    http: requests.Session,
    api_key: str,
    term: str,
    extra_params: dict,
) -> Iterator[dict]:
    """Yield every raw resource dict from all pages of a search."""
    page = 1
    while True:
        params: dict = {
            "term": term,
            "page": page,
            "limit": _PAGE_LIMIT,
            **extra_params,
        }
        logger.debug("GET %s  params=%s", _RESOURCES_URL, params)
        resp = http.get(
            _RESOURCES_URL,
            headers=_build_headers(api_key),
            params=params,
            timeout=30,
        )
        if resp.status_code == 422:
            # Some filter combos are unsupported by the API — skip silently.
            logger.debug("Skipping unsupported filter combo: %s", params)
            return
        resp.raise_for_status()

        body = resp.json()
        items: list[dict] = body.get("data", [])
        for item in items:
            yield item

        pagination = body.get("meta", {}).get("pagination", {})
        total_pages = int(pagination.get("total_pages", pagination.get("last_page", 1)))
        logger.debug("Page %d/%d  (%d items)", page, total_pages, len(items))

        if page >= total_pages or not items:
            break
        page += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Filter parameter sets for each tier.
_TIER_PARAMS: list[tuple[str, bool, dict]] = [
    # (license_label,  is_ai,  extra_params)
    ("free",    False, {"filters[license][value]": "free"}),
    ("premium", False, {"filters[license][value]": "premium"}),
    # AI-generated assets — no license filter (they exist in both tiers).
    ("free",    True,  {
        "filters[license][value]": "free",
        "filters[content_type][ai][generated]": "1",
    }),
    ("premium", True,  {
        "filters[license][value]": "premium",
        "filters[content_type][ai][generated]": "1",
    }),
]


def search(
    query: str,
    *,
    api_key: str | None = None,
    max_pages: int | None = None,
    resolve_download_urls: bool = True,
) -> list[Resource]:
    """Search Freepik and return all matching :class:`Resource` objects.

    Covers basic/free files, premium files, and AI-generated artwork in a
    single call.  Every available result page is fetched automatically unless
    *max_pages* is given.

    Args:
        query: Search term (e.g. ``"sunset landscape"``).
        api_key: Freepik API key; falls back to ``FREEPIK_API_KEY`` env var.
        max_pages: Optional cap on pages fetched per tier (useful in tests).
        resolve_download_urls: When *True* (default), resources whose
            ``download_url`` is not included in the search response are
            resolved via an extra API call.

    Returns:
        Deduplicated list of :class:`Resource` objects sorted by ID.
    """
    key = _get_api_key(api_key)
    http = requests.Session()

    seen_ids: set[int] = set()
    results: list[Resource] = []

    for license_label, is_ai, extra_params in _TIER_PARAMS:
        tag = "[AI]" if is_ai else ""
        logger.info(
            "Searching Freepik %s%s for %r …", license_label.upper(), tag, query
        )

        page_count = 0
        for raw in _iter_pages(http, key, query, extra_params):
            resource = _parse_resource(raw, license_label, is_ai)
            if resource is None or resource.id in seen_ids:
                continue

            # Resolve download URL if not already present.
            if not resource.download_url and resolve_download_urls:
                resource.download_url = _fetch_download_url(http, resource.id, key)

            if resource.download_url:
                seen_ids.add(resource.id)
                results.append(resource)
            else:
                logger.debug(
                    "Skipping resource %s — no download URL available.", resource.id
                )

            # Honour max_pages cap (count unique pages, not items).
            # We approximate: _PAGE_LIMIT items = 1 page.
            if max_pages is not None and len(results) >= max_pages * _PAGE_LIMIT:
                break

    results.sort(key=lambda r: r.id)
    logger.info(
        "Search for %r returned %d downloadable resource(s).", query, len(results)
    )
    return results


def download_urls_from_search(
    query: str,
    *,
    api_key: str | None = None,
    max_pages: int | None = None,
) -> list[str]:
    """Convenience wrapper — return only the download URLs from :func:`search`.

    Args:
        query: Search term.
        api_key: Freepik API key.
        max_pages: Optional page cap per tier.

    Returns:
        List of direct download URL strings.
    """
    resources = search(query, api_key=api_key, max_pages=max_pages)
    return [r.download_url for r in resources if r.download_url]
