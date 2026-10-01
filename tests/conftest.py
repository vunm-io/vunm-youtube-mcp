"""Shared fixtures.

Every test runs with the YOUTUBE_* variables of the developer's shell removed
and a private, empty credentials directory, so no test can read a real token.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fakes import FakeProvider
from fastmcp import Client

from vunm_youtube_mcp import auth
from vunm_youtube_mcp.config import (
    ENV_API_KEY,
    ENV_CREDENTIALS_DIR,
    ENV_LOG_LEVEL,
    ENV_MODE,
    Mode,
    Settings,
)
from vunm_youtube_mcp.server import build_server


@pytest.fixture(autouse=True)
def restore_logging():
    """`cli.main` reconfigures the root logger; undo it after each test."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    logging.captureWarnings(False)
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture(autouse=True)
def credentials_dir(tmp_path, monkeypatch):
    for name in (ENV_MODE, ENV_API_KEY, ENV_LOG_LEVEL):
        monkeypatch.delenv(name, raising=False)
    directory = tmp_path / "credentials"
    monkeypatch.setenv(ENV_CREDENTIALS_DIR, str(directory))
    return directory


def _utc_naive(delta: timedelta) -> datetime:
    # google-auth keeps token expiry as a naive UTC datetime.
    return datetime.now(timezone.utc).replace(tzinfo=None) + delta


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def make_server(provider, credentials_dir):
    """Build a server for a mode, wired to the fake provider."""

    def _make(mode: Mode = Mode.FULL, **settings):
        return build_server(
            Settings(mode=mode, credentials_dir=credentials_dir, **settings), provider
        )

    return _make


@pytest.fixture
def call_tool(make_server):
    """Call a tool through the in-memory MCP client; returns the CallToolResult."""

    async def _call(name: str, arguments: dict | None = None, *, mode: Mode = Mode.FULL):
        async with Client(make_server(mode)) as client:
            return await client.call_tool(name, arguments or {}, raise_on_error=False)

    return _call


@pytest.fixture
def write_token(credentials_dir):
    """Write a synthetic token.json and return its path."""

    def _write(
        mode: Mode = Mode.FULL,
        *,
        scopes: list[str] | None = None,
        expired: bool = False,
        refresh_token: str | None = "example-refresh-token",
    ):
        expiry = _utc_naive(timedelta(hours=-1) if expired else timedelta(hours=1))
        info = {
            "token": "example-access-token",
            "client_id": "example-client-id.apps.googleusercontent.com",
            "client_secret": "example-client-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": list(auth.scopes_for(mode)) if scopes is None else scopes,
            "expiry": expiry.isoformat() + "Z",
        }
        if refresh_token is not None:
            info["refresh_token"] = refresh_token
        credentials_dir.mkdir(parents=True, exist_ok=True)
        path = credentials_dir / "token.json"
        path.write_text(json.dumps(info), encoding="utf-8")
        return path

    return _write
