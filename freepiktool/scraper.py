"""Scrape every downloadable format link from a Freepik resource detail page.

For each Freepik file page this module:

1. Fetches the page HTML with the user's authenticated session so that
   subscription-gated links are visible.
2. Parses the page with *BeautifulSoup* to find every download anchor /
   button element.
3. Filters to the supported formats: **JPEG, PNG, SVG, EPS** and any
   **high-resolution** photo variant.
4. Follows the redirect chain of each link with the authenticated session so
   that we capture the final direct-download URL, not the intermediary
   Freepik redirect.

Supported format detection
--------------------------
A download link is included when *any* of the following is true:

* Its ``href`` or ``data-url``/``data-download-url`` attribute ends with a
  supported extension (``.jpg``, ``.jpeg``, ``.png``, ``.svg``, ``.eps``).
* Its visible text or a sibling label contains one of the format names
  (case-insensitive).
* It carries a ``data-format`` attribute whose value is a supported format.
* It is labelled as "high resolution", "highres", "HD", "4K", "2K", or "XL".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FREEPIK_BASE = "https://www.freepik.com"

# File extensions we care about.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {"jpg", "jpeg", "png", "svg", "eps"}
)

# Keywords that identify a high-resolution variant even without an extension.
_HIGHRES_KEYWORDS: frozenset[str] = frozenset(
    {"high resolution", "highres", "high-res", "hd", "4k", "2k", "xl", "large"}
)

# CSS / attribute selectors (evaluated in order; first match wins per element).
_DOWNLOAD_SELECTORS: list[str] = [
    "a[data-cy='download-button']",
    "a[data-download]",
    "a[data-download-url]",
    "a.download-button",
    "a.js-download",
    "a[href*='/download/']",
    "a[href*='download?']",
    "button[data-download-url]",
    "button[data-url]",
]

# Extension regex applied to URLs.
_EXT_RE = re.compile(
    r"\.(?P<ext>jpe?g|png|svg|eps)(?:[?#]|$)",
    re.IGNORECASE,
)

# Highres label regex applied to element text / labels.
_HIGHRES_RE = re.compile(
    r"\b(?:high[\s\-]?res(?:olution)?|highres|hd|[24]k|xl|large)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FormatLink:
    """A single downloadable format discovered on a resource page."""

    fmt: str           # Normalised format string, e.g. "jpg", "png", "svg", "eps", "highres"
    url: str           # Direct download URL (after redirect resolution)
    label: str = ""    # Human-readable label extracted from the page
    extra: dict = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.fmt.upper()}] {self.label!r} → {self.url}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_fmt(text: str, url: str) -> str | None:
    """Return a normalised format string, or *None* if the format is not supported."""
    # Check URL extension first.
    m = _EXT_RE.search(url)
    if m:
        ext = m.group("ext").lower().replace("jpeg", "jpg")
        return ext

    # Check element text / label for format name.
    text_lower = text.lower()
    for ext in ("jpeg", "jpg", "png", "svg", "eps"):
        if ext in text_lower:
            return "jpg" if ext == "jpeg" else ext

    # Check for high-res keywords.
    if _HIGHRES_RE.search(text):
        return "highres"

    return None


def _element_text(el) -> str:
    """Return all visible text from *el* and its descendants, stripped."""
    return " ".join(el.stripped_strings)


def _resolve_url(href: str, base: str = _FREEPIK_BASE) -> str:
    """Make *href* absolute, resolving it against *base* if needed."""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base, href)


def _follow_redirect(session: requests.Session, url: str, timeout: int = 20) -> str:
    """HEAD-follow redirects and return the final URL without downloading the body.

    Falls back to *url* unchanged on any error so the caller always gets
    *something* rather than raising.
    """
    try:
        resp = session.head(url, allow_redirects=True, timeout=timeout)
        return str(resp.url)
    except requests.RequestException as exc:
        logger.debug("HEAD redirect failed for %s: %s", url, exc)
    # Some servers reject HEAD — try GET with stream.
    try:
        resp = session.get(url, allow_redirects=True, stream=True, timeout=timeout)
        resp.close()
        return str(resp.url)
    except requests.RequestException as exc:
        logger.debug("GET redirect failed for %s: %s", url, exc)
        return url


def _extract_href(el) -> str:
    """Pull a raw URL out of the most likely attribute of *el*."""
    for attr in ("href", "data-download-url", "data-url", "data-download"):
        val = el.get(attr, "")
        if val and val not in ("#", "javascript:void(0)", "javascript:;"):
            return val
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_format_links(
    page_url: str,
    session: requests.Session,
    *,
    resolve_redirects: bool = True,
    timeout: int = 30,
) -> list[FormatLink]:
    """Return all supported-format download links found on *page_url*.

    Args:
        page_url: URL of the Freepik resource detail page.
        session: Authenticated :class:`requests.Session` — required so that
            subscription-gated download buttons are rendered in the HTML.
        resolve_redirects: When *True* (default), each candidate link is
            HEAD-fetched to follow any redirect chain before being returned.
        timeout: HTTP request timeout in seconds.

    Returns:
        List of :class:`FormatLink` objects, deduplicated by final URL.
    """
    logger.debug("Scraping format links from %s", page_url)

    try:
        resp = session.get(page_url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Could not fetch resource page %s: %s", page_url, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    seen_urls: set[str] = set()
    results: list[FormatLink] = []

    # Collect all candidate elements from the various selectors.
    candidates: list = []
    for selector in _DOWNLOAD_SELECTORS:
        try:
            candidates.extend(soup.select(selector))
        except (AttributeError, ValueError, NotImplementedError):
            pass

    # Also grab any <a> whose href contains a supported extension directly.
    for a in soup.find_all("a", href=_EXT_RE):
        if a not in candidates:
            candidates.append(a)

    for el in candidates:
        raw_href = _extract_href(el)
        if not raw_href:
            continue

        abs_url = _resolve_url(raw_href)

        # Determine format from URL + visible text.
        label = _element_text(el)
        fmt = _normalise_fmt(label, abs_url)
        if fmt is None:
            # Check data-format attribute as a last resort.
            data_fmt = (el.get("data-format") or "").lower()
            fmt = _normalise_fmt(data_fmt, "")
        if fmt is None:
            continue

        # Resolve the redirect chain once so we store the real file URL.
        final_url = _follow_redirect(session, abs_url) if resolve_redirects else abs_url

        # Deduplicate by final URL.
        if final_url in seen_urls:
            continue
        seen_urls.add(final_url)

        # Also deduplicate by the path portion in case protocol / domain differ.
        parsed_path = urlparse(final_url).path
        if any(urlparse(u).path == parsed_path for u in seen_urls if u != final_url):
            continue

        results.append(FormatLink(fmt=fmt, url=final_url, label=label))
        logger.debug("Found %s link: %s", fmt.upper(), final_url)

    logger.info(
        "Scraped %d format link(s) from %s  (%s)",
        len(results),
        page_url,
        ", ".join(sorted({r.fmt for r in results})) or "none",
    )
    return results


def scrape_all_download_urls(
    page_url: str,
    session: requests.Session,
    *,
    resolve_redirects: bool = True,
    timeout: int = 30,
) -> list[str]:
    """Convenience wrapper — return only the URL strings from :func:`scrape_format_links`.

    Args:
        page_url: Freepik resource detail page URL.
        session: Authenticated session.
        resolve_redirects: Follow redirect chains (default *True*).
        timeout: HTTP timeout in seconds.

    Returns:
        Deduplicated list of direct download URL strings.
    """
    links = scrape_format_links(
        page_url, session, resolve_redirects=resolve_redirects, timeout=timeout
    )
    return [lnk.url for lnk in links]
