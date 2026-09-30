"""The server registers exactly the v0.1 tool set."""

from fastmcp import Client

from vunm_youtube_mcp.server import mcp

V01_TOOLS = {
    "youtube_channel_stats",
    "youtube_analytics_report",
    "youtube_video_analytics",
    "youtube_list_videos",
    "youtube_get_video",
    "youtube_update_video",
    "youtube_get_transcript",
    "youtube_get_comments",
}


async def test_lists_exactly_the_v01_tools() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert sorted(tool.name for tool in tools) == sorted(V01_TOOLS)
