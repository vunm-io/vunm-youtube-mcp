"""Settings come from the environment and reject values they cannot use."""

from pathlib import Path

import pytest

from vunm_youtube_mcp.config import ConfigError, Mode, Settings, default_credentials_dir


def test_defaults():
    settings = Settings.from_env({})

    assert settings.mode is Mode.FULL
    assert settings.log_level == "WARNING"
    assert settings.api_key is None
    assert settings.credentials_dir == default_credentials_dir()
    assert settings.credentials_dir.name == "vunm-youtube-mcp"
    assert settings.token_file == settings.credentials_dir / "token.json"


def test_reads_and_normalizes_every_variable():
    settings = Settings.from_env(
        {
            "YOUTUBE_MCP_MODE": " Read-Only ",
            "YOUTUBE_CREDENTIALS_DIR": "~/example-credentials",
            "YOUTUBE_API_KEY": " example-api-key ",
            "YOUTUBE_MCP_LOG_LEVEL": "debug",
        }
    )

    assert settings.mode is Mode.READ_ONLY
    assert settings.credentials_dir == Path("~/example-credentials").expanduser()
    assert settings.api_key == "example-api-key"
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    ("name", "value"),
    [("YOUTUBE_MCP_MODE", "readonly"), ("YOUTUBE_MCP_LOG_LEVEL", "verbose")],
)
def test_rejects_invalid_values(name, value):
    with pytest.raises(ConfigError, match=name):
        Settings.from_env({name: value})
