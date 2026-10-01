"""Channel, upload, video and comment tools against a fake Data API client."""

from fakes import (
    CHANNEL_ID,
    UPLOADS_ID,
    channel_response,
    comment_thread,
    http_error,
    playlist_page,
    video_item,
)


async def test_channel_stats(provider, call_tool):
    provider.data_client.respond("channels.list", channel_response())

    result = await call_tool("youtube_channel_stats")

    assert not result.is_error
    stats = result.structured_content
    assert stats["channel_id"] == CHANNEL_ID
    assert stats["subscriber_count"] == "1200"
    assert stats["uploads_playlist_id"] == UPLOADS_ID
    assert provider.data_client.calls_to("channels.list") == [
        {"mine": True, "part": "snippet,contentDetails,statistics"}
    ]


async def test_channel_stats_without_a_channel(provider, call_tool):
    provider.data_client.respond("channels.list", {"items": []})

    result = await call_tool("youtube_channel_stats")

    assert result.is_error
    assert "has no YouTube channel" in result.content[0].text


async def test_list_videos_pages_and_caches_the_uploads_playlist(provider, make_server):
    from fastmcp import Client

    data = provider.data_client
    data.respond("channels.list", channel_response())
    data.respond(
        "playlistItems.list",
        playlist_page(["vid00000001", "vid00000002"], next_page_token="PAGE2"),
        playlist_page(["vid00000003"]),
    )
    data.respond(
        "videos.list",
        {"items": [video_item("vid00000001"), video_item("vid00000002")]},
        {"items": [video_item("vid00000003")]},
    )

    async with Client(make_server()) as client:
        first = await client.call_tool("youtube_list_videos", {"max_results": 2})
        second = await client.call_tool(
            "youtube_list_videos", {"max_results": 2, "page_token": "PAGE2"}
        )

    assert [v["video_id"] for v in first.structured_content["videos"]] == [
        "vid00000001",
        "vid00000002",
    ]
    assert first.structured_content["next_page_token"] == "PAGE2"
    assert first.structured_content["videos"][0]["privacy_status"] == "private"
    assert first.structured_content["videos"][0]["view_count"] == "10"
    assert second.structured_content["next_page_token"] is None
    assert len(data.calls_to("channels.list")) == 1
    pages = data.calls_to("playlistItems.list")
    assert pages[0] == {
        "playlistId": UPLOADS_ID,
        "part": "snippet,status,contentDetails",
        "maxResults": 2,
    }
    assert pages[1]["pageToken"] == "PAGE2"
    assert data.calls_to("videos.list")[0]["id"] == "vid00000001,vid00000002"


async def test_list_videos_rejects_a_page_size_over_50(provider, call_tool):
    result = await call_tool("youtube_list_videos", {"max_results": 51})

    assert result.is_error
    assert "less than or equal to 50" in result.content[0].text
    assert provider.data_client.calls == []


async def test_get_video(provider, call_tool):
    provider.data_client.respond("videos.list", {"items": [video_item("vid00000001")]})

    result = await call_tool("youtube_get_video", {"video_id": "vid00000001"})

    video = result.structured_content
    assert video["title"] == "Video vid00000001"
    assert video["tags"] == ["example", "synthetic"]
    assert video["duration"] == "PT4M13S"


async def test_get_video_not_found(provider, call_tool):
    provider.data_client.respond("videos.list", {"items": []})

    result = await call_tool("youtube_get_video", {"video_id": "vid00000001"})

    assert result.is_error
    assert "vid00000001 was not found" in result.content[0].text


async def test_get_video_rejects_a_malformed_id(provider, call_tool):
    result = await call_tool("youtube_get_video", {"video_id": "not-an-id"})

    assert result.is_error
    assert "String should match pattern" in result.content[0].text
    assert provider.data_client.calls == []


async def test_get_comments_as_plain_text(provider, call_tool):
    provider.data_client.respond(
        "commentThreads.list", {"items": [comment_thread("cmt1", "Great video")]}
    )

    result = await call_tool("youtube_get_comments", {"video_id": "vid00000001", "max_results": 5})

    assert result.structured_content["result"] == [
        {
            "comment_id": "cmt1",
            "author": "Example Viewer",
            "text": "Great video",
            "like_count": 3,
            "published_at": "2026-09-02T00:00:00Z",
            "total_reply_count": 1,
        }
    ]
    assert provider.data_client.calls_to("commentThreads.list") == [
        {
            "videoId": "vid00000001",
            "part": "snippet",
            "maxResults": 5,
            "order": "relevance",
            "textFormat": "plainText",
        }
    ]


async def test_get_comments_when_disabled(provider, call_tool):
    provider.data_client.respond("commentThreads.list", http_error(403, "commentsDisabled"))

    result = await call_tool("youtube_get_comments", {"video_id": "vid00000001"})

    assert result.is_error
    assert "Comments are disabled for this video" in result.content[0].text


async def test_get_comments_rejects_more_than_100(provider, call_tool):
    result = await call_tool(
        "youtube_get_comments", {"video_id": "vid00000001", "max_results": 101}
    )

    assert result.is_error
    assert provider.data_client.calls == []
