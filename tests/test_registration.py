"""What the server advertises in tools/list, and what building it does not do."""

import pytest
from fastmcp import Client

from vunm_youtube_mcp import server as server_module
from vunm_youtube_mcp.config import Mode, Settings
from vunm_youtube_mcp.server import VIDEO_ID_PATTERN, build_server

CHANNEL_TOOLS = {
    "youtube_channel_stats",
    "youtube_analytics_report",
    "youtube_video_analytics",
    "youtube_list_videos",
}
PUBLIC_TOOLS = {
    "youtube_get_video",
    "youtube_get_comments",
    "youtube_get_transcript",
    "youtube_search_videos",
}
READ_TOOLS = CHANNEL_TOOLS | PUBLIC_TOOLS
WRITE_TOOLS = {"youtube_update_video"}


async def _tools(server):
    async with Client(server) as client:
        return {tool.name: tool for tool in await client.list_tools()}


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (Mode.FULL, READ_TOOLS | WRITE_TOOLS),
        (Mode.READ_ONLY, READ_TOOLS),
        (Mode.PUBLIC, PUBLIC_TOOLS),
    ],
)
async def test_lists_the_tools_of_each_mode(make_server, mode, expected):
    assert set(await _tools(make_server(mode))) == expected


async def test_the_write_tool_is_annotated_destructive_and_idempotent(make_server):
    annotations = (await _tools(make_server()))["youtube_update_video"].annotations

    assert annotations.read_only_hint is False
    assert annotations.destructive_hint is True
    assert annotations.idempotent_hint is True


def test_instructions_follow_the_mode(make_server):
    full = make_server(Mode.FULL).instructions
    read_only = make_server(Mode.READ_ONLY).instructions

    public = make_server(Mode.PUBLIC).instructions

    assert "dry_run=false only after they confirm" in full
    assert "cannot change the channel" in read_only
    assert "no access to a channel's private data" in public
    assert all("authorization is needed" in text for text in (full, read_only, public))


async def test_read_tools_are_annotated_read_only_with_titles(make_server):
    tools = await _tools(make_server())
    assert len(tools) == 9

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
