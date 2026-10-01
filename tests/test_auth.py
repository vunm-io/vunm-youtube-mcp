"""Loading, refreshing and saving OAuth tokens; the auth command; the no-token tool error."""

from __future__ import annotations

import json
import logging
import os
import stat
import subprocess
import sys
from datetime import timedelta

import pytest
from fastmcp import Client
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from vunm_youtube_mcp import auth, cli
from vunm_youtube_mcp.config import Mode, Settings
from vunm_youtube_mcp.server import build_server

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")


def _settings(mode: Mode = Mode.FULL) -> Settings:
    return Settings(mode=mode, credentials_dir=Settings.from_env().credentials_dir)


def _mode_bits(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _refresh_must_not_run(self, request):
    raise AssertionError("a valid token must not be refreshed")


def test_valid_token_loads_without_refresh(write_token, monkeypatch):
    write_token()
    monkeypatch.setattr(Credentials, "refresh", _refresh_must_not_run)

    creds = auth.load_credentials(_settings())

    assert creds.token == "example-access-token"
    assert set(creds.scopes) == set(auth.scopes_for(Mode.FULL))


@posix_only
def test_expired_token_refreshes_and_is_saved_privately(
    write_token, monkeypatch, capsys, caplog, credentials_dir
):
    token_file = write_token(expired=True)

    def fake_refresh(self, request):
        self.token = "fresh-access-token"
        self.expiry = self.expiry + timedelta(hours=2)

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)
    caplog.set_level(logging.INFO, logger="vunm_youtube_mcp")

    creds = auth.load_credentials(_settings())

    assert creds.token == "fresh-access-token"
    assert json.loads(token_file.read_text(encoding="utf-8"))["token"] == "fresh-access-token"
    assert _mode_bits(token_file) == 0o600
    assert sorted(p.name for p in credentials_dir.iterdir()) == ["token.json"]
    assert capsys.readouterr().out == ""
    assert "Refreshing the expired access token" in caplog.text


def test_refresh_error_requires_auth(write_token, monkeypatch):
    write_token(expired=True)

    def failing_refresh(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(Credentials, "refresh", failing_refresh)

    with pytest.raises(auth.AuthRequired) as raised:
        auth.load_credentials(_settings())

    message = str(raised.value)
    assert "invalid_grant" in message
    assert "`vunm-youtube-mcp auth`" in message
    assert "7 days" in message


def test_expired_token_without_refresh_token_requires_auth(write_token):
    write_token(expired=True, refresh_token="")

    with pytest.raises(auth.AuthRequired, match="no refresh token"):
        auth.load_credentials(_settings())


def test_missing_token_requires_auth():
    with pytest.raises(auth.AuthRequired, match="no saved token"):
        auth.load_credentials(_settings())


def test_unreadable_token_requires_auth(write_token):
    write_token().write_text("{not json", encoding="utf-8")

    with pytest.raises(auth.AuthRequired, match="cannot be read"):
        auth.load_credentials(_settings())


def test_scope_mismatch_requires_auth_for_that_mode(write_token, monkeypatch):
    write_token(Mode.FULL)
    monkeypatch.setattr(Credentials, "refresh", _refresh_must_not_run)

    with pytest.raises(auth.AuthRequired) as raised:
        auth.load_credentials(_settings(Mode.READ_ONLY))

    message = str(raised.value)
    assert "read-only mode needs [youtube.readonly, yt-analytics.readonly]" in message
    assert "`vunm-youtube-mcp auth --mode read-only`" in message


def test_public_mode_has_no_oauth_scopes():
    with pytest.raises(ValueError, match="public mode does not use OAuth"):
        auth.scopes_for(Mode.PUBLIC)


@posix_only
def test_save_token_creates_a_private_directory_and_file(tmp_path):
    token_file = tmp_path / "new" / "dir" / "token.json"
    creds = Credentials(token="example-access-token", refresh_token="example-refresh-token")

    auth.save_token(creds, token_file)

    assert _mode_bits(token_file.parent) == 0o700
    assert _mode_bits(token_file) == 0o600
    assert json.loads(token_file.read_text(encoding="utf-8"))["token"] == "example-access-token"


def test_invalid_mode_exits_with_code_2(tmp_path):
    env = {key: value for key, value in os.environ.items() if not key.startswith("YOUTUBE_")}
    env.update({"YOUTUBE_MCP_MODE": "bogus", "YOUTUBE_CREDENTIALS_DIR": str(tmp_path)})

    completed = subprocess.run(
        [sys.executable, "-m", "vunm_youtube_mcp", "serve"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 2
    assert "invalid YOUTUBE_MCP_MODE='bogus'" in completed.stderr
    assert completed.stdout == ""


async def test_tool_call_without_token_returns_the_auth_hint(monkeypatch):
    def browser_flow(*args, **kwargs):
        raise AssertionError("a tool call must never start the browser flow")

    monkeypatch.setattr(InstalledAppFlow, "from_client_secrets_file", browser_flow)
    monkeypatch.setattr(InstalledAppFlow, "run_local_server", browser_flow)

    async with Client(build_server(Settings.from_env())) as client:
        result = await client.call_tool("youtube_channel_stats", {}, raise_on_error=False)

    assert result.is_error
    text = result.content[0].text
    assert "YouTube authorization needed: no saved token" in text
    assert "`vunm-youtube-mcp auth`" in text
    assert "7 days" in text


class _FakeFlow:
    def __init__(self, scopes):
        self.scopes = scopes

    def run_local_server(self, **kwargs):
        assert kwargs["prompt"] == "consent"
        return Credentials(
            token="example-access-token",
            refresh_token="example-refresh-token",
            scopes=self.scopes,
        )


@posix_only
@pytest.mark.parametrize("mode", [Mode.FULL, Mode.READ_ONLY])
def test_auth_command_saves_a_token_for_the_mode(mode, credentials_dir, monkeypatch, capsys):
    credentials_dir.mkdir(parents=True)
    (credentials_dir / "client_secret.json").write_text("{}", encoding="utf-8")
    requested = {}

    def from_client_secrets_file(path, scopes):
        requested["scopes"] = scopes
        return _FakeFlow(scopes)

    monkeypatch.setattr(InstalledAppFlow, "from_client_secrets_file", from_client_secrets_file)
    monkeypatch.setattr(cli, "_channel_title", lambda creds: "Example Channel")

    assert cli.main(["auth", "--mode", mode.value]) == 0

    token_file = credentials_dir / "token.json"
    assert requested["scopes"] == list(auth.scopes_for(mode))
    assert _mode_bits(token_file) == 0o600
    out = capsys.readouterr().out
    assert f"Token written to {token_file}" in out
    assert "Authorized channel: Example Channel" in out


def test_auth_command_explains_setup_when_there_is_no_client_secret(
    credentials_dir, monkeypatch, capsys
):
    monkeypatch.setattr(auth, "legacy_credentials_dirs", list)

    assert cli.main(["auth"]) == 1

    out = capsys.readouterr().out
    assert f"No OAuth client secret in {credentials_dir}" in out
    assert "7 days" in out
    assert credentials_dir.is_dir()


def test_auth_command_points_at_v01_credentials_without_moving_them(
    tmp_path, credentials_dir, monkeypatch, capsys
):
    legacy = tmp_path / "checkout" / "credentials"
    legacy.mkdir(parents=True)
    (legacy / "client_secret.json").write_text("{}", encoding="utf-8")
    (legacy / "token.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(auth, "legacy_credentials_dirs", lambda: [legacy])

    assert cli.main(["auth"]) == 1

    out = capsys.readouterr().out
    assert f"Found v0.1 credentials in {legacy}" in out
    assert str(credentials_dir) in out
    assert sorted(p.name for p in legacy.iterdir()) == ["client_secret.json", "token.json"]
    assert not any(credentials_dir.iterdir())


def test_legacy_dirs_include_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert tmp_path / "credentials" in auth.legacy_credentials_dirs()


def test_auth_command_refuses_public_mode(monkeypatch, capsys):
    monkeypatch.setenv("YOUTUBE_MCP_MODE", "public")

    assert cli.main(["auth"]) == 2
    assert "needs no authorization" in capsys.readouterr().err
