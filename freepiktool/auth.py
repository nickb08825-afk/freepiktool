"""Authentication helpers for Freepik.

Freepik requires an active session (cookie) obtained by logging in.  This
module handles credential management and session creation so that the
downloader can make authenticated requests.

Credentials can be supplied via:
  - environment variables  FREEPIK_EMAIL / FREEPIK_PASSWORD
  - a .env file in the working directory
  - explicit keyword arguments
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://www.freepik.com/login"
_LOGIN_API_URL = "https://www.freepik.com/api/user/login"

# Headers that mimic a real browser to avoid trivial bot-detection.
_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.freepik.com/",
}


def get_credentials(
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[str, str]:
    """Return (email, password), falling back to environment variables.

    Raises:
        ValueError: if either credential cannot be found.
    """
    email = email or os.getenv("FREEPIK_EMAIL")
    password = password or os.getenv("FREEPIK_PASSWORD")
    if not email:
        raise ValueError(
            "Freepik email not provided. "
            "Set FREEPIK_EMAIL in your environment or pass --email."
        )
    if not password:
        raise ValueError(
            "Freepik password not provided. "
            "Set FREEPIK_PASSWORD in your environment or pass --password."
        )
    return email, password


def create_session(
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> requests.Session:
    """Log in to Freepik and return an authenticated :class:`requests.Session`.

    The session retains cookies for subsequent download requests.

    Args:
        email: Freepik account e-mail. Falls back to FREEPIK_EMAIL env var.
        password: Freepik password. Falls back to FREEPIK_PASSWORD env var.

    Returns:
        An authenticated :class:`requests.Session`.

    Raises:
        ValueError: if credentials are missing.
        RuntimeError: if login fails.
    """
    email, password = get_credentials(email, password)

    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)

    # Fetch the login page first so we pick up any initial cookies / CSRF tokens.
    logger.debug("Fetching login page …")
    resp = session.get(_LOGIN_URL, timeout=30)
    resp.raise_for_status()

    payload = {"email": email, "password": password, "remember": True}

    logger.debug("Posting credentials …")
    login_resp = session.post(
        _LOGIN_API_URL,
        json=payload,
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )

    if login_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Login failed (HTTP {login_resp.status_code}): {login_resp.text[:200]}"
        )

    data = login_resp.json()
    if not data.get("success") and data.get("error"):
        raise RuntimeError(f"Login rejected by Freepik: {data.get('error')}")

    logger.info("Logged in as %s", email)
    return session
