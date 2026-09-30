"""OAuth 2.0 credentials for the YouTube Data and Analytics APIs.

Tools only *load* credentials: `load_credentials` reads the saved token,
refreshes it when it has expired and raises `AuthRequired` when that is not
possible. Only the interactive `vunm-youtube-mcp auth` command runs the
browser flow (`run_auth_flow`), so a tool call never blocks on a browser.
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from fastmcp.exceptions import ToolError
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from vunm_youtube_mcp.config import Mode, Settings

logger = logging.getLogger(__name__)

SCOPE_PREFIX = "https://www.googleapis.com/auth/"
YOUTUBE = SCOPE_PREFIX + "youtube"
YOUTUBE_READONLY = SCOPE_PREFIX + "youtube.readonly"
YT_ANALYTICS_READONLY = SCOPE_PREFIX + "yt-analytics.readonly"

SCOPES: dict[Mode, tuple[str, ...]] = {
    Mode.FULL: (YOUTUBE, YT_ANALYTICS_READONLY),
    Mode.READ_ONLY: (YOUTUBE_READONLY, YT_ANALYTICS_READONLY),
}

TESTING_EXPIRY_NOTE = (
    "If the OAuth consent screen of your Google Cloud project is in Testing status, "
    "Google expires its refresh tokens after 7 days; publishing the app to "
    "In production avoids that."
)


def scopes_for(mode: Mode) -> tuple[str, ...]:
    """The OAuth scopes a mode needs. `public` mode uses an API key instead."""
    try:
        return SCOPES[mode]
    except KeyError:
        raise ValueError(f"{mode} mode does not use OAuth") from None


def auth_command(mode: Mode) -> str:
    """The command that authorizes `mode`."""
    if mode is Mode.FULL:
        return "vunm-youtube-mcp auth"
    return f"vunm-youtube-mcp auth --mode {mode}"


def _short(scopes) -> str:
    return ", ".join(sorted(scope.removeprefix(SCOPE_PREFIX) for scope in scopes)) or "none"


class AuthRequired(ToolError):
    """There is no usable token; the user has to run `vunm-youtube-mcp auth`."""

    def __init__(self, reason: str, mode: Mode) -> None:
        self.reason = reason
        self.mode = mode
        super().__init__(
            f"YouTube authorization needed: {reason}. Run `{auth_command(mode)}` in a "
            f"terminal, then retry. {TESTING_EXPIRY_NOTE}"
        )


def load_credentials(settings: Settings) -> Credentials:
    """Load the saved token for `settings.mode`, refreshing it when it has expired.

    Never opens a browser. Raises `AuthRequired` when the token is missing or
    unreadable, was granted other scopes than the mode needs, or cannot be
    refreshed.
    """
    mode = settings.mode
    required = scopes_for(mode)
    token_file = settings.token_file
    if not token_file.is_file():
        raise AuthRequired(f"no saved token at {token_file}", mode)

    try:
        creds = Credentials.from_authorized_user_file(str(token_file))
    except (OSError, ValueError) as exc:
        raise AuthRequired(f"the token at {token_file} cannot be read ({exc})", mode) from exc

    granted = set(creds.scopes or ())
    if granted != set(required):
        raise AuthRequired(
            f"the saved token grants [{_short(granted)}] but {mode} mode needs "
            f"[{_short(required)}]",
            mode,
        )

    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise AuthRequired("the saved token has expired and has no refresh token", mode)

    logger.info("Refreshing the expired access token")
    try:
        creds.refresh(Request())
    except RefreshError as exc:
        detail = exc.args[0] if exc.args else exc
        raise AuthRequired(f"Google refused to refresh the saved token ({detail})", mode) from exc
    save_token(creds, token_file)
    return creds


def ensure_private_dir(directory: Path) -> None:
    """Create `directory` readable by its owner only (0700) if it does not exist."""
    if directory.is_dir():
        return
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)


def save_token(creds: Credentials, token_file: Path) -> None:
    """Write the token atomically, readable by its owner only (0600)."""
    directory = token_file.parent
    ensure_private_dir(directory)
    fd, tmp_name = tempfile.mkstemp(prefix=".token-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(creds.to_json())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, token_file)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise
    logger.info("Saved the token to %s", token_file)


def find_client_secret(directory: Path) -> Path | None:
    """`client_secret.json`, or the `client_secret_*.json` name Google downloads."""
    exact = directory / "client_secret.json"
    if exact.is_file():
        return exact
    matches = sorted(path for path in directory.glob("client_secret*.json") if path.is_file())
    return matches[0] if matches else None


def run_auth_flow(settings: Settings, client_secret: Path) -> Credentials:
    """Authorize in the browser and save the token. Interactive: for the CLI only."""
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret), scopes=list(scopes_for(settings.mode))
    )
    # prompt=consent makes Google return a refresh token on every authorization.
    creds = flow.run_local_server(port=0, prompt="consent")
    save_token(creds, settings.token_file)
    return creds


def legacy_credentials_dirs() -> list[Path]:
    """Where v0.1 kept credentials: `credentials/` in the checkout (or the current dir)."""
    source_checkout = Path(__file__).resolve().parents[2] / "credentials"
    return list(dict.fromkeys([Path.cwd() / "credentials", source_checkout]))


def find_legacy_credentials(settings: Settings) -> Path | None:
    """A v0.1 credentials directory with files in it, while the new one has none."""
    if find_client_secret(settings.credentials_dir) or settings.token_file.exists():
        return None
    for candidate in legacy_credentials_dirs():
        if candidate.resolve() == settings.credentials_dir.resolve():
            continue
        has_files = find_client_secret(candidate) or (candidate / "token.json").is_file()
        if candidate.is_dir() and has_files:
            return candidate
    return None


# Service clients, built on first use. Settings come from the environment,
# which `serve` validated at startup.
_youtube_data_service: Resource | None = None
_youtube_analytics_service: Resource | None = None


def get_youtube_data_service() -> Resource:
    """An authenticated YouTube Data API v3 client."""
    global _youtube_data_service
    if _youtube_data_service is None:
        creds = load_credentials(Settings.from_env())
        _youtube_data_service = build("youtube", "v3", credentials=creds, cache_discovery=False)
    return _youtube_data_service


def get_youtube_analytics_service() -> Resource:
    """An authenticated YouTube Analytics API v2 client."""
    global _youtube_analytics_service
    if _youtube_analytics_service is None:
        creds = load_credentials(Settings.from_env())
        _youtube_analytics_service = build(
            "youtubeAnalytics", "v2", credentials=creds, cache_discovery=False
        )
    return _youtube_analytics_service
