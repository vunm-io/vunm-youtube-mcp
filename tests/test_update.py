"""youtube_update_video: preview by default, a minimal and preserving write, limits."""

import pytest
from fakes import video_item
from fastmcp import Client

from vunm_youtube_mcp import studio
from vunm_youtube_mcp.config import Mode

VIDEO_ID = "vid00000001"


def _current(**status):
    video = video_item(
        VIDEO_ID,
        title="Old title",
        tags=["alpha", "beta", "gamma"],
        defaultLanguage="vi",
        defaultAudioLanguage="vi",
        channelId="UCexampleChannel00000000",
        thumbnails={"default": {"url": "https://example.invalid/t.jpg"}},
        localized={"title": "Old title", "description": "A synthetic description."},
    )
    video["status"] = {
        "uploadStatus": "processed",
        "privacyStatus": "private",
        "license": "youtube",
        "embeddable": False,
        "publicStatsViewable": True,
        "madeForKids": False,
        "selfDeclaredMadeForKids": False,
        **status,
    }
    return {"items": [video]}


async def test_dry_run_shows_the_diff_and_warnings_without_writing(provider, call_tool):
    provider.data_client.respond("videos.list", _current())

    result = await call_tool(
        "youtube_update_video",
        {"video_id": VIDEO_ID, "title": "New title", "tags": ["alpha"], "privacy_status": "public"},
    )

    assert result.structured_content == {
        "dry_run": True,
        "video_id": VIDEO_ID,
        "changes": {
            "title": {"before": "Old title", "after": "New title"},
            "tags": {"before": ["alpha", "beta", "gamma"], "after": ["alpha"]},
            "privacy_status": {"before": "private", "after": "public"},
        },
        "warnings": [
            "The video becomes public: anyone can find and watch it.",
            "Replacing the tags drops 2 existing tag(s): ['beta', 'gamma'].",
        ],
        "quota_cost": 50,
    }
    assert provider.data_client.calls_to("videos.update") == []


async def test_no_change_means_no_write(provider, call_tool):
    provider.data_client.respond("videos.list", _current())

    result = await call_tool(
        "youtube_update_video",
        {"video_id": VIDEO_ID, "title": "Old title", "privacy_status": "private", "dry_run": False},
    )

    assert result.structured_content == {"changed": False, "video_id": VIDEO_ID}
    assert provider.data_client.calls_to("videos.update") == []


async def test_preview_then_apply(provider, make_server):
    data = provider.data_client
    data.respond("videos.list", _current(), _current())
    data.respond(
        "videos.update",
        {
            "id": VIDEO_ID,
            "snippet": {"title": "New title"},
            "status": {"privacyStatus": "unlisted"},
        },
    )
    arguments = {"video_id": VIDEO_ID, "title": "New title", "privacy_status": "unlisted"}

    async with Client(make_server()) as client:
        preview = await client.call_tool("youtube_update_video", arguments)
        applied = await client.call_tool("youtube_update_video", {**arguments, "dry_run": False})

    assert preview.structured_content["dry_run"] is True
    assert applied.structured_content["dry_run"] is False
    assert applied.structured_content["changes"] == preview.structured_content["changes"]
    assert applied.structured_content["applied"] == {
        "title": "New title",
        "privacy_status": "unlisted",
    }
    [update] = data.calls_to("videos.update")
    assert update["part"] == "snippet,status"
    assert update["body"] == {
        "id": VIDEO_ID,
        "snippet": {
            "title": "New title",
            "description": "A synthetic description.",
            "tags": ["alpha", "beta", "gamma"],
            "categoryId": "27",
            "defaultLanguage": "vi",
            "defaultAudioLanguage": "vi",
        },
        "status": {
            "privacyStatus": "unlisted",
            "license": "youtube",
            "embeddable": False,
            "publicStatsViewable": True,
            "selfDeclaredMadeForKids": False,
        },
    }


async def test_only_changed_parts_are_written(provider, call_tool):
    provider.data_client.respond("videos.list", _current())
    provider.data_client.respond(
        "videos.update", {"id": VIDEO_ID, "status": {"privacyStatus": "unlisted"}}
    )

    await call_tool(
        "youtube_update_video",
        {"video_id": VIDEO_ID, "privacy_status": "unlisted", "dry_run": False},
    )

    [update] = provider.data_client.calls_to("videos.update")
    assert update["part"] == "status"
    assert "snippet" not in update["body"]


async def test_leaving_private_clears_a_scheduled_publish_time(provider, call_tool):
    current = _current(publishAt="2026-12-01T09:00:00Z")
    provider.data_client.respond("videos.list", current, current)
    provider.data_client.respond(
        "videos.update", {"id": VIDEO_ID, "status": {"privacyStatus": "public"}}
    )
    arguments = {"video_id": VIDEO_ID, "privacy_status": "public"}

    preview = await call_tool("youtube_update_video", arguments)
    await call_tool("youtube_update_video", {**arguments, "dry_run": False})

    assert (
        "The scheduled publish time (2026-12-01T09:00:00Z) is cleared."
        in preview.structured_content["warnings"]
    )
    [update] = provider.data_client.calls_to("videos.update")
    assert "publishAt" not in update["body"]["status"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"title": "x" * 101}, "title has 101 characters; the limit is 100"),
        ({"title": "   "}, "title cannot be empty"),
        ({"title": "a <b> title"}, "title cannot contain < or >"),
        ({"description": "ế" * 1700}, "description is 5100 bytes in UTF-8; the limit is 5000"),
        ({"description": "1 > 0"}, "description cannot contain < or >"),
        ({"tags": ["ok", ""]}, "tags cannot contain an empty tag"),
        ({"tags": ["two words"] * 46}, "tags add up to 551 characters"),
        ({"category_id": "Education"}, "String should match pattern"),
    ],
)
async def test_limits_are_checked_before_any_request(provider, call_tool, arguments, message):
    result = await call_tool("youtube_update_video", {"video_id": VIDEO_ID, **arguments})

    assert result.is_error
    assert message in result.content[0].text
    assert provider.data_client.calls == []


def test_tags_length_counts_commas_and_quotes_like_youtube():
    assert studio.tags_length(["Foo-Baz"]) == 7
    assert studio.tags_length(["Foo Baz"]) == 9
    assert studio.tags_length(["a", "b c"]) == 1 + 1 + 5
    assert studio.tags_length([]) == 0


async def test_read_only_mode_has_no_write_tool(provider, call_tool):
    result = await call_tool("youtube_update_video", {"video_id": VIDEO_ID}, mode=Mode.READ_ONLY)

    assert result.is_error
    assert provider.data_client.calls == []
