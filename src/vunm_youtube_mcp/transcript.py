"""Video transcripts from YouTube's caption tracks, without YouTube Data API quota."""

from __future__ import annotations

import re
from typing import Any

from fastmcp.exceptions import ToolError
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL_PATTERNS = (
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"[?&]v=([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})"),
)


def extract_video_id(url_or_id: str) -> str:
    """The 11-character video ID in a raw ID or a YouTube URL."""
    candidate = url_or_id.strip()
    if VIDEO_ID.match(candidate):
        return candidate
    for pattern in _URL_PATTERNS:
        match = pattern.search(candidate)
        if match:
            return match.group(1)
    raise ToolError(f"{url_or_id!r} is not a YouTube video ID or URL.")


def format_timestamp(seconds: float) -> str:
    """Seconds as MM:SS, or HH:MM:SS from one hour on."""
    total = int(seconds)
    hours, minutes, secs = total // 3600, (total % 3600) // 60, total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def get_video_transcript(
    video_id_or_url: str, languages: list[str], include_timestamps: bool
) -> dict[str, Any]:
    """The transcript of a video in the first available language of `languages`."""
    video_id = extract_video_id(video_id_or_url)
    try:
        segments = YouTubeTranscriptApi().fetch(video_id, languages=languages).to_raw_data()
    except TranscriptsDisabled as exc:
        raise ToolError(f"Transcripts are disabled for video {video_id}.") from exc
    except NoTranscriptFound as exc:
        raise ToolError(f"Video {video_id} has no transcript in {languages}.") from exc
    except Exception as exc:
        raise ToolError(f"Could not retrieve the transcript of {video_id}: {exc}") from exc

    lines, texts = [], []
    for segment in segments:
        text = segment.get("text", "").strip()
        texts.append(text)
        if include_timestamps:
            lines.append(f"[{format_timestamp(segment.get('start', 0.0))}] {text}")
        else:
            lines.append(text)
    return {
        "video_id": video_id,
        "segment_count": len(segments),
        "raw_text": " ".join(texts),
        "formatted_transcript": "\n".join(lines),
    }
