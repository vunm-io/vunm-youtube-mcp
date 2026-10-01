"""Video transcripts from YouTube's caption tracks, without YouTube Data API quota.

Two backends, tried in order:

1. youtube-transcript-api (always installed).
2. yt-dlp (the optional ``ytdlp`` extra), when the first one is blocked (for
   example YouTube's ``RequestBlocked``/``IpBlocked`` for cloud IPs) or fails
   unexpectedly. It is not tried when the answer is definitive: transcripts
   disabled, no transcript in the requested languages, or no such video.

Both prefer a manually created transcript in the requested language order,
then an auto-generated one, and neither writes to stdout.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from fastmcp.exceptions import ToolError
from youtube_transcript_api import (
    InvalidVideoId,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGES = ("vi", "en")
DEFAULT_MAX_CHARS = 50_000
INSTALL_YTDLP = (
    "the ytdlp extra, for example: uvx --from "
    '"vunm-youtube-mcp[ytdlp] @ git+https://github.com/vunm-io/vunm-youtube-mcp" '
    "vunm-youtube-mcp. yt-dlp also needs Deno (or another JavaScript runtime it supports)"
)

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL_PATTERNS = (
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"[?&]v=([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})"),
)


@dataclass(frozen=True)
class Segment:
    text: str
    start: float
    duration: float


@dataclass(frozen=True)
class Transcript:
    segments: list[Segment]
    language_code: str
    language: str
    is_generated: bool
    source: str


Backend = Callable[[str, Sequence[str]], Transcript]


class TranscriptUnavailable(ToolError):
    """A definitive answer about the video; another backend would not help."""


class FallbackMissing(ToolError):
    """The yt-dlp extra is not installed."""


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


# --- youtube-transcript-api -------------------------------------------------


def fetch_with_transcript_api(video_id: str, languages: Sequence[str]) -> Transcript:
    """The first backend: youtube-transcript-api's list, then fetch."""
    try:
        listing = YouTubeTranscriptApi().list(video_id)
    except TranscriptsDisabled as exc:
        raise TranscriptUnavailable(f"Transcripts are disabled for video {video_id}.") from exc
    except (VideoUnavailable, InvalidVideoId) as exc:
        raise TranscriptUnavailable(f"Video {video_id} is not available.") from exc

    try:
        chosen = listing.find_manually_created_transcript(languages)
    except NoTranscriptFound:
        try:
            chosen = listing.find_generated_transcript(languages)
        except NoTranscriptFound as exc:
            manual = sorted(t.language_code for t in listing if not t.is_generated)
            generated = sorted(t.language_code for t in listing if t.is_generated)
            raise TranscriptUnavailable(
                _no_transcript_message(video_id, languages, manual, generated)
            ) from exc

    fetched = chosen.fetch()
    return Transcript(
        segments=[Segment(s.text, s.start, s.duration) for s in fetched],
        language_code=chosen.language_code,
        language=chosen.language,
        is_generated=chosen.is_generated,
        source="youtube-transcript-api",
    )


def _no_transcript_message(video_id, languages, manual, generated) -> str:
    return (
        f"Video {video_id} has no transcript in {list(languages)}. Available: "
        f"manual {manual or 'none'}, auto-generated {generated or 'none'}."
    )


# --- yt-dlp -------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    url: str
    language_code: str
    language: str
    is_generated: bool


def _json3_url(formats: list[dict[str, Any]] | None) -> str | None:
    for fmt in formats or []:
        if fmt.get("ext") == "json3" and fmt.get("url"):
            return fmt["url"]
    return None


def select_track(info: dict[str, Any], languages: Sequence[str]) -> Track:
    """Pick a json3 caption track from yt-dlp's video info.

    Manual subtitles come first, in language order, then auto-generated
    captions. yt-dlp lists machine translations among the automatic captions
    and marks the original language with an ``-orig`` key, so only that one
    counts as the auto-generated transcript of a language.
    """
    subtitles = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    originals = {key.removesuffix("-orig"): key for key in automatic if key.endswith("-orig")}
    if not originals:  # no translations listed: every key is an original
        originals = {key: key for key in automatic}

    for language in languages:
        url = _json3_url(subtitles.get(language))
        if url:
            name = subtitles[language][0].get("name") or language
            return Track(url, language, name, is_generated=False)
    for language in languages:
        key = originals.get(language)
        url = _json3_url(automatic.get(key)) if key else None
        if url:
            name = automatic[key][0].get("name") or language
            return Track(url, language, name, is_generated=True)
    raise TranscriptUnavailable(
        _no_transcript_message(info.get("id", "?"), languages, sorted(subtitles), sorted(originals))
    )


def parse_json3(document: dict[str, Any]) -> list[Segment]:
    """Segments from YouTube's json3 caption format (``events`` with ``segs``)."""
    segments = []
    for event in document.get("events", []):
        text = "".join(seg.get("utf8", "") for seg in event.get("segs") or []).strip()
        if not text:
            continue
        segments.append(
            Segment(
                text=text,
                start=event.get("tStartMs", 0) / 1000,
                duration=event.get("dDurationMs", 0) / 1000,
            )
        )
    return segments


class _YtDlpLog:
    """yt-dlp's logger interface, writing to this module's logger (stderr)."""

    _log = logger.getChild("yt_dlp")

    def debug(self, message: str) -> None:
        self._log.debug(message)

    def warning(self, message: str) -> None:
        self._log.warning(message)

    def error(self, message: str) -> None:
        self._log.error(message)


def ytdlp_options() -> dict[str, Any]:
    """Options that keep yt-dlp off stdout and away from downloading media."""
    return {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logtostderr": True,
        "logger": _YtDlpLog(),
    }


def fetch_with_ytdlp(video_id: str, languages: Sequence[str]) -> Transcript:
    """The fallback backend: yt-dlp's video info, then the json3 caption track."""
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
    except ImportError as exc:
        raise FallbackMissing(
            f"The yt-dlp fallback is not installed; add {INSTALL_YTDLP}."
        ) from exc

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with YoutubeDL(ytdlp_options()) as ydl:
            info = ydl.extract_info(url, download=False)
            track = select_track(info, languages)
            document = json.loads(ydl.urlopen(track.url).read())
    except DownloadError as exc:
        raise ToolError(f"yt-dlp could not read video {video_id}: {exc}") from exc
    return Transcript(
        segments=parse_json3(document),
        language_code=track.language_code,
        language=track.language,
        is_generated=track.is_generated,
        source="yt-dlp",
    )


# --- the tool -------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptBackends:
    primary: Backend = fetch_with_transcript_api
    fallback: Backend | None = fetch_with_ytdlp


def _describe(exc: BaseException) -> str:
    if isinstance(exc, RequestBlocked):
        return f"YouTube blocked the transcript request from this IP ({type(exc).__name__})"
    return f"youtube-transcript-api failed ({type(exc).__name__}: {exc})"


def get_transcript(
    video_id_or_url: str,
    languages: Sequence[str],
    include_timestamps: bool,
    max_chars: int,
    backends: TranscriptBackends,
) -> dict[str, Any]:
    """The transcript of a video, from the first backend that serves it."""
    video_id = extract_video_id(video_id_or_url)
    try:
        transcript = backends.primary(video_id, languages)
    except ToolError:
        raise
    except Exception as exc:  # blocked or unexpected: try the fallback
        reason = _describe(exc)
        if backends.fallback is None:
            raise ToolError(f"{reason}.") from exc
        logger.warning("%s; trying yt-dlp", reason)
        try:
            transcript = backends.fallback(video_id, languages)
        except FallbackMissing as missing:
            raise ToolError(f"{reason}. {missing}") from exc
        except ToolError:
            raise
        except Exception as fallback_exc:  # report both failures
            raise ToolError(f"{reason}; yt-dlp failed too ({fallback_exc}).") from fallback_exc
    return render(video_id, transcript, include_timestamps, max_chars)


def render(
    video_id: str, transcript: Transcript, include_timestamps: bool, max_chars: int
) -> dict[str, Any]:
    """The tool result: one text block, cut at a line boundary past `max_chars`."""
    lines = [
        f"[{format_timestamp(s.start)}] {s.text}" if include_timestamps else s.text
        for s in transcript.segments
    ]
    text = "\n".join(lines)
    total = len(text)
    truncated = total > max_chars
    if truncated:
        cut = text.rfind("\n", 0, max_chars + 1)
        text = text[: cut if cut > 0 else max_chars]
    return {
        "video_id": video_id,
        "language_code": transcript.language_code,
        "language": transcript.language,
        "is_generated": transcript.is_generated,
        "source": transcript.source,
        "segment_count": len(transcript.segments),
        "text": text,
        "truncated": truncated,
        "total_chars": total,
    }
