"""Runtime settings, read once from the environment.

| Variable                  | Default                             | Meaning                         |
|---------------------------|-------------------------------------|---------------------------------|
| `YOUTUBE_MCP_MODE`        | `full`                              | `full`, `read-only` or `public` |
| `YOUTUBE_CREDENTIALS_DIR` | the user config dir (platformdirs) | client secret and token         |
| `YOUTUBE_API_KEY`         | unset                               | API key, used by `public` mode  |
| `YOUTUBE_MCP_LOG_LEVEL`   | `WARNING`                           | log level; logs go to stderr    |
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import platformdirs

APP_NAME = "vunm-youtube-mcp"

ENV_MODE = "YOUTUBE_MCP_MODE"
ENV_CREDENTIALS_DIR = "YOUTUBE_CREDENTIALS_DIR"
ENV_API_KEY = "YOUTUBE_API_KEY"
ENV_LOG_LEVEL = "YOUTUBE_MCP_LOG_LEVEL"

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
TOKEN_FILENAME = "token.json"


class Mode(str, Enum):
    """What the server may do, and which credentials it uses."""

    FULL = "full"
    """Read and write the authorized channel (OAuth, write scope)."""
    READ_ONLY = "read-only"
    """Read the authorized channel (OAuth, read-only scopes); no write tool."""
    PUBLIC = "public"
    """Public data only, with an API key; no OAuth."""

    def __str__(self) -> str:
        return self.value


class ConfigError(ValueError):
    """An environment variable holds a value the server cannot use."""


def default_credentials_dir() -> Path:
    """The per-user config directory, e.g. ``~/Library/Application Support/vunm-youtube-mcp``."""
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False))


@dataclass(frozen=True)
class Settings:
    mode: Mode = Mode.FULL
    credentials_dir: Path = field(default_factory=default_credentials_dir)
    api_key: str | None = None
    log_level: str = "WARNING"

    @property
    def token_file(self) -> Path:
        return self.credentials_dir / TOKEN_FILENAME

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read the settings; raise `ConfigError` for a value that is not allowed."""
        env = os.environ if environ is None else environ

        raw_mode = env.get(ENV_MODE, "").strip().lower() or Mode.FULL.value
        try:
            mode = Mode(raw_mode)
        except ValueError:
            allowed = ", ".join(m.value for m in Mode)
            raise ConfigError(
                f"invalid {ENV_MODE}={raw_mode!r}; expected one of {allowed}"
            ) from None

        level = env.get(ENV_LOG_LEVEL, "").strip().upper() or "WARNING"
        if level not in LOG_LEVELS:
            allowed = ", ".join(LOG_LEVELS)
            raise ConfigError(f"invalid {ENV_LOG_LEVEL}={level!r}; expected one of {allowed}")

        raw_dir = env.get(ENV_CREDENTIALS_DIR, "").strip()
        credentials_dir = Path(raw_dir).expanduser() if raw_dir else default_credentials_dir()

        api_key = env.get(ENV_API_KEY, "").strip() or None
        return cls(mode=mode, credentials_dir=credentials_dir, api_key=api_key, log_level=level)
