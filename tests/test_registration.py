"""What the server advertises in tools/list, and what building it does not do."""

import pytest
from fastmcp import Client

from vunm_youtube_mcp import server as server_module
from vunm_youtube_mcp.config import Settings
from vunm_youtube_mcp.server import VIDEO_ID_PATTERN, build_server

READ_TOOLS = {
    "youtube_channel_stats",
    "youtube_analytics_report",
    "youtube_video_analytics",
    "youtube_list_videos",
    "youtube_get_video",
    "youtube_get_transcript",
    "youtube_get_comments",
}
WRITE_TOOLS = {"youtube_update_video"}


async def _tools(server):
    async with Client(server) as client:
        return {tool.name: tool for tool in await client.list_tools()}


async def test_lists_the_tools(make_server):
    assert set(await _tools(make_server())) == READ_TOOLS | WRITE_TOOLS


async def test_read_tools_are_annotated_read_only_with_titles(make_server):
    tools = await _tools(make_server())

    for name in READ_TOOLS:
        assert tools[name].annotations.read_only_hint is True, name
        assert tools[name].annotations.open_world_hint is True, name
        assert tools[name].title, name


async def test_video_ids_carry_the_pattern(make_server):
    tools = await _tools(make_server())

    for name in ("youtube_video_analytics", "youtube_get_video", "youtube_get_comments"):
        schema = tools[name].input_schema["properties"]["video_id"]
        assert schema["pattern"] == VIDEO_ID_PATTERN, name


def test_building_a_server_touches_no_credentials(monkeypatch, credentials_dir):
    def load_credentials(settings):
        raise AssertionError("building the server must not load credentials")

    monkeypatch.setattr("vunm_youtube_mcp.services.load_credentials", load_credentials)

    build_server(Settings(credentials_dir=credentials_dir))


def test_module_level_mcp_is_built_on_first_access(monkeypatch):
    monkeypatch.setattr(server_module, "_default_server", None)

    assert server_module.mcp is server_module.mcp
    with pytest.raises(AttributeError):
        _ = server_module.not_a_server
