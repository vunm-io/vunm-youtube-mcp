"""YouTube video transcript extraction module.

Extracts captions/transcripts directly without consuming YouTube Data API quota,
supporting multiple languages and formatted timestamp outputs.
"""

import re
from typing import Any

from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi


def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube 11-character video ID from a raw ID or various URL formats."""
    url_or_id = url_or_id.strip()
    # Match standard 11-character alphanumeric ID directly
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id

    # Match https://youtu.be/<id>
    short_match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url_or_id)
    if short_match:
        return short_match.group(1)

    # Match https://www.youtube.com/watch?v=<id>
    watch_match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url_or_id)
    if watch_match:
        return watch_match.group(1)

    # Match https://www.youtube.com/shorts/<id>
    shorts_match = re.search(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})", url_or_id)
    if shorts_match:
        return shorts_match.group(1)

    return url_or_id


def format_timestamp(seconds: float) -> str:
    """Convert floating-point seconds to [MM:SS] or [HH:MM:SS] format."""
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def get_video_transcript(
    video_id_or_url: str,
    languages: list[str] | None = None,
    include_timestamps: bool = True,
) -> dict[str, Any]:
    """Retrieve transcript/subtitles for a YouTube video.

    Args:
        video_id_or_url: Full YouTube URL or 11-character video ID.
        languages: List of preferred language codes, e.g. ['vi', 'en'].
        include_timestamps: If True, prefixes lines with formatted timestamps.
    """
    video_id = extract_video_id(video_id_or_url)
    lang_preference = languages or ["vi", "en"]

    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            fetched = api.fetch(video_id, languages=lang_preference)
            transcript_list = fetched.to_raw_data()
        elif hasattr(YouTubeTranscriptApi, "get_transcript"):
            transcript_list = YouTubeTranscriptApi.get_transcript(
                video_id, languages=lang_preference
            )
        else:
            raise RuntimeError("Unsupported youtube-transcript-api version.")
    except TranscriptsDisabled:
        return {"error": f"Transcripts are disabled for video '{video_id}'."}
    except NoTranscriptFound:
        return {
            "error": f"No transcript found in languages {lang_preference} for video '{video_id}'."
        }
    except Exception as e:  # noqa: BLE001 - v0.1 returns error dicts
        return {"error": f"Failed to retrieve transcript: {e}"}

    formatted_lines = []
    full_text_parts = []

    for entry in transcript_list:
        text = entry.get("text", "").strip()
        start = entry.get("start", 0.0)
        full_text_parts.append(text)
        if include_timestamps:
            formatted_lines.append(f"[{format_timestamp(start)}] {text}")
        else:
            formatted_lines.append(text)

    return {
        "video_id": video_id,
        "segment_count": len(transcript_list),
        "raw_text": " ".join(full_text_parts),
        "formatted_transcript": "\n".join(formatted_lines),
    }
