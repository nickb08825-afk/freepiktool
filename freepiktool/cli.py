"""Command-line interface for freepiktool.

**Login is required** before any download can proceed.  Credentials are
resolved in priority order:

1. ``--email`` / ``--password`` flags
2. ``FREEPIK_EMAIL`` / ``FREEPIK_PASSWORD`` environment variables (or ``.env``)
3. Interactive prompt on the terminal (hidden password input)

Usage examples
--------------
Search, scrape all formats, download and zip::

    freepiktool search "sunset landscape" --output ./downloads

Search with explicit credentials::

    freepiktool search "cats" \\
        --email me@example.com --password secret \\
        --api-key YOUR_KEY --output ./downloads

Download explicit URLs (login still required)::

    freepiktool download https://dl.freepik.com/... --output ./downloads

Download from a URL file::

    freepiktool download --url-file urls.txt --output ./downloads

Show help::

    freepiktool --help
    freepiktool search --help
    freepiktool download --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .auth import create_session
from .downloader import download

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _add_auth_args(parser: argparse.ArgumentParser) -> None:
    """Attach ``--email`` / ``--password`` arguments to *parser*."""
    parser.add_argument(
        "--email",
        metavar="EMAIL",
        help="Freepik account email (overrides FREEPIK_EMAIL env var).",
    )
    parser.add_argument(
        "--password",
        metavar="PASSWORD",
        help="Freepik account password (overrides FREEPIK_PASSWORD env var).",
    )


def _add_download_args(parser: argparse.ArgumentParser) -> None:
    """Attach shared download-tuning arguments to *parser*."""
    parser.add_argument(
        "--output", "-o",
        default=".",
        metavar="DIR",
        help="Directory to save downloaded files (default: current directory).",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=5,
        metavar="N",
        help="Number of simultaneous downloads (default: 5).",
    )
    parser.add_argument(
        "--retries", "-r",
        type=int,
        default=3,
        metavar="N",
        help="Retry count for failed downloads (default: 3).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        metavar="SECS",
        help="Per-request timeout in seconds (default: 120).",
    )


def _require_session(args: argparse.Namespace) -> object:
    """Return an authenticated session, prompting interactively if needed.

    This is the **mandatory login gate** — every command that touches Freepik
    files calls this before doing anything else.

    Returns:
        An authenticated :class:`requests.Session`.

    Raises:
        SystemExit: on authentication failure.
    """
    try:
        # interactive=True → falls back to terminal prompt when env vars / flags
        # are absent, ensuring the user is always asked to log in.
        return create_session(
            email=getattr(args, "email", None),
            password=getattr(args, "password", None),
            interactive=True,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"\n✗ Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freepiktool",
        description=(
            "Download Freepik assets faster and more efficiently.\n\n"
            "Login to your Freepik account is required for every command."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose / debug logging.",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ------------------------------------------------------------------ #
    # search sub-command                                                   #
    # ------------------------------------------------------------------ #
    sc = sub.add_parser(
        "search",
        help=(
            "Search Freepik, download every format of every result "
            "(JPEG/PNG/SVG/EPS/high-res, basic + premium + AI), "
            "and zip everything into <query>.zip."
        ),
        description=(
            "Search Freepik for QUERY.  For each result the tool visits the "
            "resource's detail page and clicks every download link "
            "(JPEG, PNG, SVG, EPS, high-resolution photo).  "
            "All downloaded files are bundled into <QUERY>.zip."
        ),
    )
    sc.add_argument("query", metavar="QUERY", help="Search term, e.g. \"sunset landscape\".")
    sc.add_argument(
        "--api-key", "-k",
        metavar="KEY",
        help="Freepik API key (overrides FREEPIK_API_KEY env var).",
    )
    sc.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Cap the number of result pages fetched per tier (default: all pages).",
    )
    sc.add_argument(
        "--keep-files",
        action="store_true",
        help="Keep individual downloaded files after creating the zip archive.",
    )
    _add_auth_args(sc)
    _add_download_args(sc)

    # ------------------------------------------------------------------ #
    # download sub-command                                                 #
    # ------------------------------------------------------------------ #
    dl = sub.add_parser(
        "download",
        help="Download one or more explicit Freepik direct-download URLs.",
        description=(
            "Download one or more Freepik direct-download URLs.\n\n"
            "Login is required — credentials are taken from flags, environment "
            "variables, or an interactive prompt."
        ),
    )

    url_group = dl.add_mutually_exclusive_group(required=True)
    url_group.add_argument(
        "urls",
        nargs="*",
        metavar="URL",
        default=[],
        help="One or more direct download URLs.",
    )
    url_group.add_argument(
        "--url-file", "-f",
        metavar="FILE",
        help="Path to a text file containing one URL per line.",
    )

    _add_auth_args(dl)
    _add_download_args(dl)

    return parser


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def _collect_urls(args: argparse.Namespace) -> list[str]:
    """Return URLs from CLI positional args or a URL file."""
    if args.url_file:
        path = Path(args.url_file)
        if not path.is_file():
            print(f"Error: URL file not found: {path}", file=sys.stderr)
            sys.exit(1)
        lines = path.read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return [u for u in args.urls if u.strip()]


def _cmd_download(args: argparse.Namespace) -> int:
    """Handle the ``download`` sub-command."""
    # ── Mandatory login ────────────────────────────────────────────────── #
    session = _require_session(args)

    urls = _collect_urls(args)
    if not urls:
        print("Error: no URLs provided.", file=sys.stderr)
        return 1

    saved = download(
        urls,
        dest_dir=args.output,
        session=session,
        concurrency=args.concurrency,
        retries=args.retries,
        timeout_secs=args.timeout,
    )

    total = len(urls)
    ok = len(saved)
    failed = total - ok
    print(f"\n✓ {ok}/{total} file(s) downloaded successfully.", file=sys.stderr)
    if failed:
        print(f"✗ {failed} file(s) failed.", file=sys.stderr)
        return 1
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Handle the ``search`` sub-command.

    Pipeline:
        1. Mandatory login
        2. Search Freepik (basic + premium + AI) via the API
        3. For each result, scrape every format download link
           (JPEG / PNG / SVG / EPS / high-res) from the detail page
        4. Download all collected URLs concurrently
        5. Zip everything into ``<query>.zip`` in *--output*
    """
    from .search import search as freepik_search
    from .zipper import zip_results

    # ── 1. Mandatory login ─────────────────────────────────────────────── #
    session = _require_session(args)

    # ── 2 & 3. Search + scrape all format links ────────────────────────── #
    print(f"\n🔍  Searching Freepik for {args.query!r} …", file=sys.stderr)
    try:
        resources = freepik_search(
            args.query,
            api_key=getattr(args, "api_key", None),
            session=session,
            max_pages=args.max_pages,
        )
    except ValueError as exc:
        print(f"Search error: {exc}", file=sys.stderr)
        return 1

    if not resources:
        print("No results found.", file=sys.stderr)
        return 0

    # Flatten all format URLs from every resource.
    all_urls: list[str] = []
    seen: set[str] = set()
    for resource in resources:
        for url in resource.all_download_urls():
            if url and url not in seen:
                seen.add(url)
                all_urls.append(url)

    if not all_urls:
        print("Found resources but no downloadable URLs.", file=sys.stderr)
        return 1

    print(
        f"   Found {len(resources)} resource(s) → {len(all_urls)} download URL(s).",
        file=sys.stderr,
    )

    # ── 4. Download all URLs concurrently ──────────────────────────────── #
    saved = download(
        all_urls,
        dest_dir=args.output,
        session=session,
        concurrency=args.concurrency,
        retries=args.retries,
        timeout_secs=args.timeout,
    )

    if not saved:
        print("✗ No files downloaded successfully.", file=sys.stderr)
        return 1

    # ── 5. Zip into <query>.zip ────────────────────────────────────────── #
    try:
        archive = zip_results(
            saved,
            query=args.query,
            dest_dir=args.output,
            remove_originals=not args.keep_files,
        )
    except (ValueError, OSError) as exc:
        print(f"✗ Failed to create zip archive: {exc}", file=sys.stderr)
        return 1

    total = len(all_urls)
    ok = len(saved)
    failed = total - ok
    print(f"\n✓ {ok}/{total} file(s) downloaded.", file=sys.stderr)
    if failed:
        print(f"  ✗ {failed} file(s) failed.", file=sys.stderr)
    print(f"  📦 Archive: {archive}", file=sys.stderr)
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:  # noqa: D401
    """Entry-point for the ``freepiktool`` command."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "download":
        sys.exit(_cmd_download(args))

    if args.command == "search":
        sys.exit(_cmd_search(args))

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
