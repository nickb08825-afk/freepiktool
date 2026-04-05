"""Authentication helpers for Freepik.

Freepik requires an active session (cookie) obtained by logging in.
**Login is mandatory** — no downloads are permitted without a valid
authenticated session so that membership / subscription entitlements
(premium files, AI artwork, high-resolution exports) are correctly applied.

Credentials are resolved in this order of precedence:
  1. Explicit keyword arguments (``email`` / ``password``)
  2. Environment variables ``FREEPIK_EMAIL`` / ``FREEPIK_PASSWORD``
  3. A ``.env`` file in the working directory
  4. Interactive prompt (terminal stdin/stderr) — used as the final fallback
     so the tool always asks rather than silently failing.
"""

from __future__ import annotations

import getpass
import logging
import os
import sys
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


def _prompt_credentials() -> tuple[str, str]:
    """Interactively ask for email and password on the terminal.

    Password input is hidden (uses :func:`getpass.getpass`).
    """
    print(
        "\n╔══════════════════════════════════════════════════╗\n"
        "║  Freepik login required to access your           ║\n"
        "║  membership / subscription downloads.            ║\n"
        "╚══════════════════════════════════════════════════╝\n",
        file=sys.stderr,
    )
    email = input("  Freepik email: ").strip()
    if not email:
        raise ValueError("Email cannot be empty.")
    password = getpass.getpass("  Freepik password: ")
    if not password:
        raise ValueError("Password cannot be empty.")
    return email, password


def get_credentials(
    email: Optional[str] = None,
    password: Optional[str] = None,
    *,
    interactive: bool = True,
) -> tuple[str, str]:
    """Return ``(email, password)``, prompting interactively as a last resort.

    Args:
        email: Explicit email; falls back to ``FREEPIK_EMAIL`` env var.
        password: Explicit password; falls back to ``FREEPIK_PASSWORD`` env var.
        interactive: When *True* (default) and credentials are still missing,
            prompt the user on the terminal.

    Returns:
        ``(email, password)`` tuple — always non-empty strings.

    Raises:
        ValueError: if credentials cannot be obtained.
    """
    email = email or os.getenv("FREEPIK_EMAIL")
    password = password or os.getenv("FREEPIK_PASSWORD")

    if not email or not password:
        if not interactive:
            missing = []
            if not email:
                missing.append("FREEPIK_EMAIL")
            if not password:
                missing.append("FREEPIK_PASSWORD")
            raise ValueError(
                f"Missing credentials: {', '.join(missing)}. "
                "Set them in your environment, a .env file, or pass --email/--password."
            )
        # Fall through to interactive prompt — fill in only what is missing.
        prompted_email, prompted_password = _prompt_credentials()
        email = email or prompted_email
        password = password or prompted_password

    return email, password  # type: ignore[return-value]


def create_session(
    email: Optional[str] = None,
    password: Optional[str] = None,
    *,
    interactive: bool = True,
) -> requests.Session:
    """Log in to Freepik and return an authenticated :class:`requests.Session`.

    **Login is mandatory.** If credentials are not available via arguments or
    environment variables the user is prompted interactively (unless
    ``interactive=False``).

    The returned session retains cookies so every subsequent download request
    automatically carries the user's subscription entitlements.

    Args:
        email: Freepik account e-mail.
        password: Freepik account password.
        interactive: Prompt on the terminal when credentials are missing.

    Returns:
        An authenticated :class:`requests.Session`.

    Raises:
        ValueError: if credentials are missing and ``interactive=False``.
        RuntimeError: if the login request is rejected by Freepik.
    """
    email, password = get_credentials(email, password, interactive=interactive)

    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)

    # Fetch the login page first to pick up any initial cookies / CSRF tokens.
    logger.debug("Fetching login page …")
    resp = session.get(_LOGIN_URL, timeout=30)
    resp.raise_for_status()

    payload = {"email": email, "password": password, "remember": True}

    logger.debug("Posting credentials …")
    login_resp = session.post(
        _LOGIN_API_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    # Clear the credentials dict from local scope immediately so sensitive
    # data cannot appear in log output or exception tracebacks below.
    del payload, password

    if login_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Login failed (HTTP {login_resp.status_code}): {login_resp.text[:200]}"
        )

    data = login_resp.json()
    if not data.get("success") and data.get("error"):
        raise RuntimeError(f"Login rejected by Freepik: {data.get('error')}")

    logger.info("Logged in as %s", email)
    return session
