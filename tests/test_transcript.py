"""The transcript tool, with youtube-transcript-api replaced by a fake."""

import pytest
from fastmcp.exceptions import ToolError
from youtube_transcript_api import (
    FetchedTranscript,
    FetchedTranscriptSnippet,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from vunm_youtube_mcp.transcript import extract_video_id, format_timestamp


@pytest.mark.parametrize(
    "value",
    [
        "vid00000001",
        " vid00000001 ",
        "https://www.youtube.com/watch?v=vid00000001&t=42",
        "https://youtu.be/vid00000001",
        "https://www.youtube.com/shorts/vid00000001",
        "https://www.youtube.com/live/vid00000001?feature=share",
    ],
)
def test_extracts_the_video_id(value):
    assert extract_video_id(value) == "vid00000001"


def test_rejects_something_that_is_not_a_video():
    with pytest.raises(ToolError, match="is not a YouTube video ID or URL"):
        extract_video_id("https://example.com/watch")


def test_formats_timestamps():
    assert format_timestamp(75.9) == "01:15"
    assert format_timestamp(3725) == "01:02:05"


async def test_transcript_with_timestamps(monkeypatch, call_tool):
    requested = {}

    def fetch(self, video_id, languages):
        requested.update(video_id=video_id, languages=languages)
        snippets = [
            FetchedTranscriptSnippet(text="Xin chào", start=0.0, duration=1.5),
            FetchedTranscriptSnippet(text=" the end ", start=75.2, duration=2.0),
        ]
        return FetchedTranscript(snippets, video_id, "Vietnamese", "vi", is_generated=False)

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch", fetch)

    result = await call_tool(
        "youtube_get_transcript", {"video_id_or_url": "https://youtu.be/vid00000001"}
    )

    assert requested == {"video_id": "vid00000001", "languages": ["vi", "en"]}
    assert result.structured_content["formatted_transcript"] == "[00:00] Xin chào\n[01:15] the end"
    assert result.structured_content["raw_text"] == "Xin chào the end"


async def test_disabled_transcripts(monkeypatch, call_tool):
    def fetch(self, video_id, languages):
        raise TranscriptsDisabled(video_id)

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch", fetch)

    result = await call_tool("youtube_get_transcript", {"video_id_or_url": "vid00000001"})

    assert result.is_error
    assert "Transcripts are disabled for video vid00000001" in result.content[0].text
