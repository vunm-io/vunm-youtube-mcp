"""Authentication module for YouTube APIs using OAuth 2.0.

Handles token persistence, automatic token refresh, and initial browser-based
authorization for Desktop Application credentials.
"""

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

logger = logging.getLogger(__name__)

# Scopes required for YouTube Data API v3 and YouTube Analytics API
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Base directory for storing credentials (the repository root when run from source)
DEFAULT_CREDENTIALS_DIR = Path(__file__).resolve().parents[2] / "credentials"


def get_credentials_dir() -> Path:
    """Return the credentials directory path."""
    custom_dir = os.environ.get("YOUTUBE_CREDENTIALS_DIR")
    if custom_dir:
        path = Path(custom_dir)
    else:
        path = DEFAULT_CREDENTIALS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_client_secret_file() -> Path | None:
    """Find the client_secret.json file in the credentials directory."""
    creds_dir = get_credentials_dir()

    # Check exact name first
    standard_path = creds_dir / "client_secret.json"
    if standard_path.exists():
        return standard_path

    # Look for client_secret_*.json pattern from Google Cloud Console download
    patterns = list(creds_dir.glob("client_secret*.json"))
    if patterns:
        return patterns[0]

    return None


def get_credentials() -> Credentials:
    """Retrieve or generate user OAuth2 credentials.

    If credentials/token.json exists and is valid, load it.
    If expired, refresh it automatically.
    If nonexistent, trigger the local server browser authorization flow.
    """
    creds_dir = get_credentials_dir()
    token_file = creds_dir / "token.json"
    creds: Credentials | None = None

    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as e:  # noqa: BLE001 - v0.1 falls back to a new authorization
            logger.warning("Could not load %s: %s", token_file, e)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing the expired access token")
            try:
                creds.refresh(Request())
            except Exception as e:  # noqa: BLE001 - v0.1 falls back to a new authorization
                logger.warning("Token refresh failed (%s); starting a new authorization", e)
                creds = None

        if not creds:
            secret_file = find_client_secret_file()
            if not secret_file:
                raise FileNotFoundError(
                    f"No client secret found in {creds_dir}.\n"
                    "Please download OAuth 2.0 Client ID (Desktop app) from Google Cloud Console "
                    f"and save it as '{creds_dir / 'client_secret.json'}'."
                )

            logger.warning("Opening a browser to authorize with %s", secret_file.name)
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
            # No prompt message: run_local_server prints it to stdout, which would
            # corrupt the stdio transport when this runs inside a tool call.
            creds = flow.run_local_server(port=0, authorization_prompt_message=None)

        # Save credentials for future runs
        with open(token_file, "w", encoding="utf-8") as token_out:
            token_out.write(creds.to_json())
        logger.info("Saved credentials to %s", token_file)

    return creds


_youtube_data_service: Resource | None = None
_youtube_analytics_service: Resource | None = None


def get_youtube_data_service() -> Resource:
    """Return an authenticated YouTube Data API v3 service client."""
    global _youtube_data_service
    if _youtube_data_service is None:
        creds = get_credentials()
        _youtube_data_service = build("youtube", "v3", credentials=creds, cache_discovery=False)
    return _youtube_data_service


def get_youtube_analytics_service() -> Resource:
    """Return an authenticated YouTube Analytics API v2 service client."""
    global _youtube_analytics_service
    if _youtube_analytics_service is None:
        creds = get_credentials()
        _youtube_analytics_service = build(
            "youtubeAnalytics", "v2", credentials=creds, cache_discovery=False
        )
    return _youtube_analytics_service
