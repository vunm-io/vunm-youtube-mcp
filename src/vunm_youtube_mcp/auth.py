"""Authentication module for YouTube APIs using OAuth 2.0.

Handles token persistence, automatic token refresh, and initial browser-based
authorization for Desktop Application credentials.
"""

from pathlib import Path
from typing import Optional
import os
import glob

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

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


def find_client_secret_file() -> Optional[Path]:
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
    creds: Optional[Credentials] = None

    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as e:
            print(f"[Warning] Failed to load existing token.json: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[Auth] Refreshing expired access token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[Auth] Token refresh failed ({e}), initiating re-authorization...")
                creds = None

        if not creds:
            secret_file = find_client_secret_file()
            if not secret_file:
                raise FileNotFoundError(
                    f"No client secret found in {creds_dir}.\n"
                    "Please download OAuth 2.0 Client ID (Desktop app) from Google Cloud Console "
                    f"and save it as '{creds_dir / 'client_secret.json'}'."
                )

            print(f"[Auth] Starting OAuth2 authorization flow using {secret_file.name}...")
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for future runs
        with open(token_file, "w", encoding="utf-8") as token_out:
            token_out.write(creds.to_json())
        print(f"[Auth] Credentials saved to {token_file}")

    return creds


_youtube_data_service: Optional[Resource] = None
_youtube_analytics_service: Optional[Resource] = None


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
        _youtube_analytics_service = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    return _youtube_analytics_service
