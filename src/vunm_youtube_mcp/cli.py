"""Command-line entry point: ``vunm-youtube-mcp [serve|auth]``.

``serve`` (the default) runs the MCP server over stdio. ``auth`` is the
interactive, one-time OAuth setup; it is the only command that may open a
browser or print to stdout.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence

from vunm_youtube_mcp import __version__

LOG_LEVEL_ENV = "YOUTUBE_MCP_LOG_LEVEL"
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vunm-youtube-mcp",
        description="MCP server for YouTube channel management, analytics and transcripts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="{serve,auth}")
    commands.add_parser("serve", help="run the MCP server over stdio (default)")
    commands.add_parser("auth", help="authorize access to your YouTube channel in a browser")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    args = _build_parser().parse_args(argv)
    level = os.environ.get(LOG_LEVEL_ENV, "").strip().upper() or "WARNING"
    if level not in _LOG_LEVELS:
        print(
            f"vunm-youtube-mcp: invalid {LOG_LEVEL_ENV}={level!r}; "
            f"expected one of {', '.join(_LOG_LEVELS)}",
            file=sys.stderr,
        )
        return 2
    configure_logging(level)
    if args.command == "auth":
        return _auth()
    return _serve(level)


def configure_logging(level: str) -> None:
    """Send every log record, and Python warnings, to stderr.

    Over the stdio transport, stdout carries MCP messages only.
    """
    logging.basicConfig(stream=sys.stderr, level=level, format=_LOG_FORMAT, force=True)
    logging.captureWarnings(True)


def _serve(level: str) -> int:
    from vunm_youtube_mcp.server import mcp

    mcp.run(transport="stdio", show_banner=False, log_level=level)
    return 0


def _auth() -> int:
    from vunm_youtube_mcp.auth import find_client_secret_file, get_credentials, get_credentials_dir
    from vunm_youtube_mcp.studio import get_channel_overview

    print("vunm-youtube-mcp: OAuth 2.0 setup")
    creds_dir = get_credentials_dir()
    secret_file = find_client_secret_file()
    if not secret_file:
        print(f"\nNo client secret file found in {creds_dir}.")
        print("1. Open Google Cloud Console (https://console.cloud.google.com/).")
        print("2. Create or select a project, then enable YouTube Data API v3 and")
        print("   YouTube Analytics API.")
        print("3. Configure the OAuth consent screen.")
        print("4. Credentials -> Create credentials -> OAuth client ID (type: Desktop app).")
        print(f"5. Download the JSON file and save it as {creds_dir / 'client_secret.json'}")
        return 1

    print(f"Found client secret: {secret_file.name}. Opening the browser to authorize...")
    try:
        get_credentials()
        print(f"Authorization succeeded. Token saved to {creds_dir / 'token.json'}")
        overview = get_channel_overview()
    except Exception as exc:  # noqa: BLE001 - report any failure of the interactive flow
        print(f"Authorization failed: {exc}")
        return 1

    if "error" in overview:
        print(f"Warning: the API returned an error: {overview['error']}")
    else:
        print(f"Connected to channel: {overview.get('title')}")
    return 0
