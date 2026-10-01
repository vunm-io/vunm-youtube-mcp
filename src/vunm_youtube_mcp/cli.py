"""Command-line entry point: ``vunm-youtube-mcp [serve|auth]``.

``serve`` (the default) runs the MCP server over stdio and never writes to
stdout itself. ``auth`` is the interactive OAuth setup; it is the only command
that opens a browser or prints to stdout.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from collections.abc import Sequence

from vunm_youtube_mcp import __version__
from vunm_youtube_mcp.config import ConfigError, Mode, Settings

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_README = "https://github.com/vunm-io/vunm-youtube-mcp#readme"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vunm-youtube-mcp",
        description="MCP server for YouTube channel management, analytics and transcripts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="{serve,auth}")
    commands.add_parser("serve", help="run the MCP server over stdio (default)")
    auth = commands.add_parser("auth", help="authorize access to your YouTube channel")
    auth.add_argument(
        "--mode",
        choices=[Mode.FULL.value, Mode.READ_ONLY.value],
        help="access to authorize (default: YOUTUBE_MCP_MODE, else full)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"vunm-youtube-mcp: {exc}", file=sys.stderr)
        return 2
    configure_logging(settings.log_level)
    if args.command == "auth":
        if args.mode:
            settings = dataclasses.replace(settings, mode=Mode(args.mode))
        return _auth(settings)
    return _serve(settings)


def configure_logging(level: str) -> None:
    """Send every log record, and Python warnings, to stderr.

    Over the stdio transport, stdout carries MCP messages only.
    """
    logging.basicConfig(stream=sys.stderr, level=level, format=_LOG_FORMAT, force=True)
    logging.captureWarnings(True)


def _serve(settings: Settings) -> int:
    from vunm_youtube_mcp.server import build_server

    build_server(settings).run(transport="stdio", show_banner=False, log_level=settings.log_level)
    return 0


def _auth(settings: Settings) -> int:
    from vunm_youtube_mcp import auth

    if settings.mode is Mode.PUBLIC:
        print(
            "public mode reads public data with YOUTUBE_API_KEY and needs no authorization.",
            file=sys.stderr,
        )
        return 2

    creds_dir = settings.credentials_dir
    auth.ensure_private_dir(creds_dir)
    client_secret = auth.find_client_secret(creds_dir)
    if client_secret is None:
        legacy = auth.find_legacy_credentials(settings)
        if legacy is not None:
            _print_legacy_hint(legacy, settings)
        else:
            _print_setup_steps(settings)
        return 1

    print(f"Authorizing {settings.mode} access with {client_secret.name}.")
    print("Your browser opens Google's consent page; pick the account that owns the channel.")
    try:
        creds = auth.run_auth_flow(settings, client_secret)
    except Exception as exc:  # noqa: BLE001 - report any failure of the interactive flow
        print(f"Authorization failed: {exc}", file=sys.stderr)
        return 1
    print(f"Token written to {settings.token_file}")

    title = _channel_title(creds)
    if title:
        print(f"Authorized channel: {title}")
    return 0


def _print_legacy_hint(legacy, settings: Settings) -> None:
    new = settings.credentials_dir
    print(f"Found v0.1 credentials in {legacy}.")
    print(f"This version reads them from {new}. Move them there yourself, for example:")
    print(f'  mv "{legacy}"/* "{new}"/ && chmod 600 "{new}"/*')
    print("then run `vunm-youtube-mcp auth` again.")


def _print_setup_steps(settings: Settings) -> None:
    creds_dir = settings.credentials_dir
    print(f"No OAuth client secret in {creds_dir}.")
    print("1. In Google Cloud Console, enable YouTube Data API v3 and YouTube Analytics API.")
    print("2. Configure the OAuth consent screen. In Testing status Google expires refresh")
    print("   tokens after 7 days; publish the app (In production) to avoid that.")
    print('3. Create an OAuth client ID of type "Desktop app" and download its JSON.')
    print(f"4. Save it as {creds_dir / 'client_secret.json'} and run this command again.")
    print(f"Details: {_README}")


def _channel_title(creds) -> str | None:
    """The authorized channel's title, to confirm the account; None if unavailable."""
    from googleapiclient.discovery import build

    try:
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = youtube.channels().list(mine=True, part="snippet").execute().get("items", [])
    except Exception as exc:  # noqa: BLE001 - the token is saved; this is only a check
        print(f"Warning: could not read the channel to confirm the account: {exc}")
        return None
    if not items:
        print("Warning: this Google account has no YouTube channel.")
        return None
    return items[0].get("snippet", {}).get("title")
