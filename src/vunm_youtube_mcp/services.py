"""Google API clients behind a small seam, so tools can be tested with fakes.

Tools ask a `ServiceProvider` for a client at call time. `GoogleServiceProvider`
loads the saved token on first use (never at import or startup), or uses the
API key in public mode, and builds the clients from the discovery documents
bundled with google-api-python-client, so no network call happens until a tool
actually queries YouTube.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol

from fastmcp.exceptions import ToolError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from vunm_youtube_mcp.auth import load_credentials
from vunm_youtube_mcp.config import ENV_API_KEY, Mode, Settings


class ServiceProvider(Protocol):
    """Hands out API clients (googleapiclient ``Resource`` objects)."""

    def data(self) -> Any:
        """A YouTube Data API v3 client."""
        ...

    def analytics(self) -> Any:
        """A YouTube Analytics API v2 client."""
        ...


class GoogleServiceProvider:
    """Authenticated clients, built on first use and cached.

    httplib2, under googleapiclient, is not thread-safe, and FastMCP runs sync
    tools in worker threads, so each thread gets its own clients. The loaded
    credentials are shared.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._credentials: Credentials | None = None
        self._local = threading.local()

    def _creds(self) -> Credentials:
        with self._lock:
            if self._credentials is None:
                self._credentials = load_credentials(self._settings)
            return self._credentials

    def _client(self, name: str, version: str) -> Any:
        key = f"{name}_{version}"
        client = getattr(self._local, key, None)
        if client is None:
            if self._settings.mode is Mode.PUBLIC:
                client = build(name, version, developerKey=self._api_key(), cache_discovery=False)
            else:
                client = build(name, version, credentials=self._creds(), cache_discovery=False)
            setattr(self._local, key, client)
        return client

    def _api_key(self) -> str:
        if not self._settings.api_key:
            raise ToolError(
                f"Public mode reads YouTube with an API key: set {ENV_API_KEY} in the MCP "
                "server's environment to a Google Cloud API key that can call the YouTube "
                "Data API v3."
            )
        return self._settings.api_key

    def data(self) -> Any:
        return self._client("youtube", "v3")

    def analytics(self) -> Any:
        if self._settings.mode is Mode.PUBLIC:
            raise ToolError("YouTube Analytics needs OAuth, so public mode cannot read it.")
        return self._client("youtubeAnalytics", "v2")
