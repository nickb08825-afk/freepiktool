"""Command-line interface for freepiktool.

Usage examples
--------------
Download a single file (anonymous)::

    freepiktool download https://www.freepik.com/... --output ./downloads

Download multiple URLs from a file (authenticated)::

    freepiktool download --url-file urls.txt \\
        --email me@example.com --password secret \\
        --output ./downloads --concurrency 8

Show help::

    freepiktool --help
    freepiktool download --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .downloader import download

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freepiktool",
        description="Download Freepik assets faster and more efficiently.",
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
    # download sub-command                                                 #
    # ------------------------------------------------------------------ #
    dl = sub.add_parser(
        "download",
        help="Download one or more Freepik files.",
        description="Download one or more Freepik direct-download URLs.",
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

    dl.add_argument(
        "--output", "-o",
        default=".",
        metavar="DIR",
        help="Directory to save downloaded files (default: current directory).",
    )
    dl.add_argument(
        "--concurrency", "-c",
        type=int,
        default=5,
        metavar="N",
        help="Number of simultaneous downloads (default: 5).",
    )
    dl.add_argument(
        "--retries", "-r",
        type=int,
        default=3,
        metavar="N",
        help="Retry count for failed downloads (default: 3).",
    )
    dl.add_argument(
        "--timeout",
        type=int,
        default=120,
        metavar="SECS",
        help="Per-request timeout in seconds (default: 120).",
    )
    dl.add_argument(
        "--email",
        metavar="EMAIL",
        help="Freepik account email (overrides FREEPIK_EMAIL env var).",
    )
    dl.add_argument(
        "--password",
        metavar="PASSWORD",
        help="Freepik account password (overrides FREEPIK_PASSWORD env var).",
    )

    return parser


def _collect_urls(args: argparse.Namespace) -> list[str]:
    """Return the list of URLs from CLI args or a URL file."""
    if args.url_file:
        path = Path(args.url_file)
        if not path.is_file():
            print(f"Error: URL file not found: {path}", file=sys.stderr)
            sys.exit(1)
        lines = path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    return [u for u in args.urls if u.strip()]


def _cmd_download(args: argparse.Namespace) -> int:
    """Handle the ``download`` sub-command."""
    urls = _collect_urls(args)
    if not urls:
        print("Error: no URLs provided.", file=sys.stderr)
        return 1

    session = None
    if args.email or args.password:
        from .auth import create_session  # imported lazily to keep startup fast

        try:
            session = create_session(email=args.email, password=args.password)
        except (ValueError, RuntimeError) as exc:
            print(f"Authentication error: {exc}", file=sys.stderr)
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

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
