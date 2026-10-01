"""GoogleServiceProvider: OAuth or API key per mode, clients cached per thread."""

import threading

import pytest
from fastmcp.exceptions import ToolError

from vunm_youtube_mcp import services
from vunm_youtube_mcp.config import Mode, Settings


@pytest.fixture
def built(monkeypatch):
    """Record every googleapiclient build() call instead of building a client."""
    calls = []

    def fake_build(name, version, **kwargs):
        calls.append((name, version, kwargs))
        return object()

    monkeypatch.setattr(services, "build", fake_build)
    return calls


def _provider(credentials_dir, mode, **settings):
    return services.GoogleServiceProvider(
        Settings(mode=mode, credentials_dir=credentials_dir, **settings)
    )


def test_public_mode_uses_the_api_key(built, credentials_dir, monkeypatch):
    def load_credentials(settings):
        raise AssertionError("public mode must not load a token")

    monkeypatch.setattr(services, "load_credentials", load_credentials)
    provider = _provider(credentials_dir, Mode.PUBLIC, api_key="example-api-key")

    provider.data()

    assert built == [
        ("youtube", "v3", {"developerKey": "example-api-key", "cache_discovery": False})
    ]


def test_public_mode_without_a_key_explains_what_to_set(built, credentials_dir):
    provider = _provider(credentials_dir, Mode.PUBLIC)

    with pytest.raises(ToolError, match="set YOUTUBE_API_KEY"):
        provider.data()
    assert built == []


def test_public_mode_has_no_analytics(built, credentials_dir):
    provider = _provider(credentials_dir, Mode.PUBLIC, api_key="example-api-key")

    with pytest.raises(ToolError, match="needs OAuth"):
        provider.analytics()


@pytest.mark.parametrize("mode", [Mode.FULL, Mode.READ_ONLY])
def test_oauth_modes_load_the_token_once(built, credentials_dir, monkeypatch, mode):
    loaded = []
    token = object()

    def load_credentials(settings):
        loaded.append(settings.mode)
        return token

    monkeypatch.setattr(services, "load_credentials", load_credentials)
    provider = _provider(credentials_dir, mode, api_key="ignored-in-oauth-modes")

    provider.data()
    provider.analytics()

    assert loaded == [mode]
    assert [(name, kwargs["credentials"]) for name, _, kwargs in built] == [
        ("youtube", token),
        ("youtubeAnalytics", token),
    ]


def test_clients_are_cached_per_thread(built, credentials_dir, monkeypatch):
    monkeypatch.setattr(services, "load_credentials", lambda settings: object())
    provider = _provider(credentials_dir, Mode.FULL)

    first = provider.data()
    again = provider.data()
    other = []
    worker = threading.Thread(target=lambda: other.append(provider.data()))
    worker.start()
    worker.join()

    assert first is again
    assert other[0] is not first
    assert len(built) == 2
