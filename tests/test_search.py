"""youtube_search_videos against a fake Data API client, in every mode."""

from datetime import datetime

import pytest
from fakes import http_error

from vunm_youtube_mcp.config import Mode
from vunm_youtube_mcp.search import rfc3339


def _results(*video_ids, next_page_token=None):
    response = {
        "items": [
            {
                "id": {"kind": "youtube#video", "videoId": video_id},
                "snippet": {
                    "title": "Tom &amp; Jerry&#39;s guide",
                    "description": "A &quot;synthetic&quot; result.",
                    "channelId": "UCexampleChannel00000000",
                    "channelTitle": "Example &amp; Co",
                    "publishedAt": "2026-09-01T00:00:00Z",
                    "liveBroadcastContent": "none",
                    "thumbnails": {},
                },
            }
            for video_id in video_ids
        ]
        + [{"id": {"kind": "youtube#channel", "channelId": "UCother"}, "snippet": {}}],
        "pageInfo": {"totalResults": 1234, "resultsPerPage": len(video_ids)},
    }
    if next_page_token:
        response["nextPageToken"] = next_page_token
    return response


@pytest.mark.parametrize("mode", list(Mode))
async def test_search_in_every_mode(provider, call_tool, mode):
    provider.data_client.respond("search.list", _results("vid00000001", next_page_token="NEXT"))

    result = await call_tool("youtube_search_videos", {"query": "mcp server"}, mode=mode)

    assert not result.is_error
    assert result.structured_content["next_page_token"] == "NEXT"
    assert result.structured_content["total_results"] == 1234
    [video] = result.structured_content["videos"]
    assert video["video_id"] == "vid00000001"
    assert video["title"] == "Tom & Jerry's guide"
    assert video["description"] == 'A "synthetic" result.'
    assert video["channel_title"] == "Example & Co"
    assert provider.data_client.calls_to("search.list") == [
        {
            "part": "snippet",
            "q": "mcp server",
            "type": "video",
            "maxResults": 10,
            "order": "relevance",
        }
    ]


async def test_search_with_every_filter(provider, call_tool):
    provider.data_client.respond("search.list", _results())

    await call_tool(
        "youtube_search_videos",
        {
            "query": "release notes",
            "max_results": 25,
            "channel_id": "UCexampleChannel00000000",
            "order": "date",
            "published_after": "2026-09-01T07:00:00+07:00",
            "page_token": "PAGE2",
        },
    )

    [request] = provider.data_client.calls_to("search.list")
    assert request["channelId"] == "UCexampleChannel00000000"
    assert request["order"] == "date"
    assert request["maxResults"] == 25
    assert request["publishedAfter"] == "2026-09-01T00:00:00Z"
    assert request["pageToken"] == "PAGE2"


def test_naive_times_are_taken_as_utc():
    naive = datetime(2026, 9, 1, 12, 30)  # noqa: DTZ001 - the naive case under test

    assert rfc3339(naive) == "2026-09-01T12:30:00Z"


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": ""},
        {"query": "x", "max_results": 26},
        {"query": "x", "order": "popularity"},
        {"query": "x", "channel_id": "not a channel"},
    ],
)
async def test_search_rejects_invalid_arguments(provider, call_tool, arguments):
    result = await call_tool("youtube_search_videos", arguments)

    assert result.is_error
    assert provider.data_client.calls == []


async def test_search_quota_is_explained(provider, call_tool):
    provider.data_client.respond("search.list", http_error(403, "quotaExceeded"))

    result = await call_tool("youtube_search_videos", {"query": "x"})

    assert result.is_error
    assert "search has its own bucket of 100 calls a day" in result.content[0].text


async def test_search_docstring_states_the_quota(make_server):
    from fastmcp import Client

    async with Client(make_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    description = tools["youtube_search_videos"].description
    assert "own bucket of 100 calls a day per Google Cloud" in description
    assert "each page counts as one call" in description
    assert "youtube_list_videos" in description
