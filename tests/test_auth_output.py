"""Refreshing an expired token logs to stderr and writes nothing to stdout."""

import json
import logging
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials

from vunm_youtube_mcp import auth


def _write_expired_token(directory):
    token = {
        "token": "expired-access-token",
        "refresh_token": "example-refresh-token",
        "client_id": "example-client-id.apps.googleusercontent.com",
        "client_secret": "example-client-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": auth.SCOPES,
        "expiry": "2020-01-01T00:00:00Z",
    }
    (directory / "token.json").write_text(json.dumps(token), encoding="utf-8")


def test_refresh_path_writes_nothing_to_stdout(tmp_path, monkeypatch, capsys, caplog):
    monkeypatch.setenv("YOUTUBE_CREDENTIALS_DIR", str(tmp_path))
    _write_expired_token(tmp_path)

    def fake_refresh(self, request):
        self.token = "fresh-access-token"
        self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)
    caplog.set_level(logging.INFO, logger="vunm_youtube_mcp")

    creds = auth.get_credentials()

    assert creds.token == "fresh-access-token"
    assert capsys.readouterr().out == ""
    assert "Refreshing the expired access token" in caplog.text
