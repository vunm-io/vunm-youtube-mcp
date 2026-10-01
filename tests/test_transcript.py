"""Transcripts: both backends, the fallback between them, and the tool result.

youtube-transcript-api and yt-dlp are replaced by fakes; no test reaches YouTube.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import ClassVar

import pytest
import yt_dlp
from fastmcp.exceptions import ToolError
from youtube_transcript_api import (
    FetchedTranscript,
    FetchedTranscriptSnippet,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from vunm_youtube_mcp import transcript as tr

VIDEO_ID = "vid00000001"


def _transcript(source="youtube-transcript-api", texts=("Xin chào", "the end")):
    segments = [tr.Segment(text, start * 75.2, 2.0) for start, text in enumerate(texts)]
    return tr.Transcript(segments, "vi", "Vietnamese", False, source)


# --- video IDs and timestamps -------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        VIDEO_ID,
        f" {VIDEO_ID} ",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}?feature=share",
    ],
)
def test_extracts_the_video_id(value):
    assert tr.extract_video_id(value) == VIDEO_ID


def test_rejects_something_that_is_not_a_video():
    with pytest.raises(ToolError, match="is not a YouTube video ID or URL"):
        tr.extract_video_id("https://example.com/watch")


def test_formats_timestamps():
    assert tr.format_timestamp(75.9) == "01:15"
    assert tr.format_timestamp(3725) == "01:02:05"


# --- youtube-transcript-api backend ------------------------------------------------


class _FakeTrack:
    def __init__(self, language_code, is_generated):
        self.language_code = language_code
        self.language = f"Language {language_code}"
        self.is_generated = is_generated

    def fetch(self):
        snippets = [
            FetchedTranscriptSnippet(text=f"{self.language_code} line", start=1.0, duration=2.0)
        ]
        return FetchedTranscript(
            snippets, VIDEO_ID, self.language, self.language_code, self.is_generated
        )


class _FakeListing:
    def __init__(self, *tracks):
        self.tracks = tracks

    def __iter__(self):
        return iter(self.tracks)

    def _find(self, languages, generated):
        for language in languages:
            for track in self.tracks:
                if track.language_code == language and track.is_generated is generated:
                    return track
        raise NoTranscriptFound(VIDEO_ID, languages, self)

    def find_manually_created_transcript(self, languages):
        return self._find(languages, generated=False)

    def find_generated_transcript(self, languages):
        return self._find(languages, generated=True)


@pytest.fixture
def listing(monkeypatch):
    def _use(result):
        def fake_list(self, video_id):
            if isinstance(result, BaseException):
                raise result
            return result

        monkeypatch.setattr(YouTubeTranscriptApi, "list", fake_list)

    return _use


def test_manual_transcript_wins_over_generated_in_language_order(listing):
    listing(_FakeListing(_FakeTrack("vi", True), _FakeTrack("en", False)))

    result = tr.fetch_with_transcript_api(VIDEO_ID, ["vi", "en"])

    assert (result.language_code, result.is_generated) == ("en", False)
    assert result.source == "youtube-transcript-api"
    assert result.segments == [tr.Segment("en line", 1.0, 2.0)]


def test_generated_transcript_when_there_is_no_manual_one(listing):
    listing(_FakeListing(_FakeTrack("vi", True), _FakeTrack("fr", False)))

    result = tr.fetch_with_transcript_api(VIDEO_ID, ["vi", "en"])

    assert (result.language_code, result.is_generated) == ("vi", True)


def test_no_transcript_lists_the_available_languages(listing):
    listing(_FakeListing(_FakeTrack("fr", False), _FakeTrack("de", True)))

    with pytest.raises(tr.TranscriptUnavailable) as raised:
        tr.fetch_with_transcript_api(VIDEO_ID, ["vi", "en"])

    assert "Available: manual ['fr'], auto-generated ['de']" in str(raised.value)


def test_disabled_transcripts_are_definitive(listing):
    listing(TranscriptsDisabled(VIDEO_ID))

    with pytest.raises(tr.TranscriptUnavailable, match="disabled"):
        tr.fetch_with_transcript_api(VIDEO_ID, ["vi"])


def test_a_blocked_request_is_left_to_the_fallback(listing):
    listing(IpBlocked(VIDEO_ID))

    with pytest.raises(RequestBlocked):
        tr.fetch_with_transcript_api(VIDEO_ID, ["vi"])


# --- yt-dlp backend --------------------------------------------------------


def _formats(language, *exts):
    return [
        {"ext": ext, "url": f"https://example.invalid/{language}.{ext}", "name": language}
        for ext in exts
    ]


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        # Manual subtitles in the first language.
        ({"subtitles": {"vi": _formats("vi", "vtt", "json3")}}, ("vi", False)),
        # Manual subtitles come before auto-generated ones, even in a later language.
        (
            {
                "subtitles": {"en": _formats("en", "json3")},
                "automatic_captions": {
                    "vi-orig": _formats("vi-orig", "json3"),
                    "vi": _formats("vi", "json3"),
                },
            },
            ("en", False),
        ),
        # Auto-generated: the original language, not a machine translation.
        (
            {
                "automatic_captions": {
                    "vi": _formats("vi", "json3"),
                    "en": _formats("en", "json3"),
                    "en-orig": _formats("en-orig", "json3"),
                }
            },
            ("en", True),
        ),
        # Without "-orig" keys there are no translations, so every key is original.
        ({"automatic_captions": {"vi": _formats("vi", "json3")}}, ("vi", True)),
        # A track without json3 is skipped.
        (
            {
                "subtitles": {"vi": _formats("vi", "vtt")},
                "automatic_captions": {"en-orig": _formats("en-orig", "json3")},
            },
            ("en", True),
        ),
    ],
)
def test_track_selection(info, expected):
    track = tr.select_track(info, ["vi", "en"])

    assert (track.language_code, track.is_generated) == expected
    assert track.url.endswith(".json3")


def test_track_selection_without_a_match_lists_what_exists():
    info = {
        "id": VIDEO_ID,
        "subtitles": {"fr": _formats("fr", "json3")},
        "automatic_captions": {
            "de-orig": _formats("de-orig", "json3"),
            "vi": _formats("vi", "json3"),
        },
    }

    with pytest.raises(tr.TranscriptUnavailable) as raised:
        tr.select_track(info, ["vi", "en"])

    assert "Available: manual ['fr'], auto-generated ['de']" in str(raised.value)


JSON3 = {
    "events": [
        {"tStartMs": 0, "dDurationMs": 1500, "segs": [{"utf8": "Xin"}, {"utf8": " chào"}]},
        {"tStartMs": 1500, "dDurationMs": 10, "aAppend": 1, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 2000, "dDurationMs": 500},
        {"tStartMs": 75200, "dDurationMs": 2000, "segs": [{"utf8": "the end "}]},
    ]
}


def test_parses_json3():
    assert tr.parse_json3(JSON3) == [
        tr.Segment("Xin chào", 0.0, 1.5),
        tr.Segment("the end", 75.2, 2.0),
    ]


class _FakeYoutubeDL:
    instances: ClassVar[list[_FakeYoutubeDL]] = []
    info: ClassVar[dict] = {}
    error: ClassVar[Exception | None] = None

    def __init__(self, params):
        self.params = params
        self.opened = []
        _FakeYoutubeDL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        assert download is False
        self.extracted = url
        if self.error:
            raise self.error
        return self.info

    def urlopen(self, url):
        self.opened.append(url)
        return _Response(json.dumps(JSON3).encode())


class _Response:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body


@pytest.fixture
def fake_ytdlp(monkeypatch):
    _FakeYoutubeDL.instances = []
    _FakeYoutubeDL.error = None
    _FakeYoutubeDL.info = {
        "id": VIDEO_ID,
        "automatic_captions": {"vi-orig": _formats("vi-orig", "json3")},
    }
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYoutubeDL)
    return _FakeYoutubeDL


def test_ytdlp_backend_fetches_the_chosen_track_quietly(fake_ytdlp):
    result = tr.fetch_with_ytdlp(VIDEO_ID, ["vi", "en"])

    [ydl] = fake_ytdlp.instances
    assert ydl.extracted == f"https://www.youtube.com/watch?v={VIDEO_ID}"
    assert ydl.opened == ["https://example.invalid/vi-orig.json3"]
    assert {
        key: ydl.params[key] for key in ("skip_download", "quiet", "no_warnings", "logtostderr")
    } == {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "logtostderr": True,
    }
    assert callable(ydl.params["logger"].debug)
    assert (result.source, result.language_code, result.is_generated) == ("yt-dlp", "vi", True)
    assert result.segments[0] == tr.Segment("Xin chào", 0.0, 1.5)


def test_ytdlp_errors_become_tool_errors(fake_ytdlp):
    fake_ytdlp.error = yt_dlp.utils.DownloadError("Sign in to confirm you are not a bot")

    with pytest.raises(ToolError, match="yt-dlp could not read video"):
        tr.fetch_with_ytdlp(VIDEO_ID, ["vi"])


def test_ytdlp_logs_go_to_the_logging_system(caplog):
    caplog.set_level(logging.DEBUG, logger="vunm_youtube_mcp")
    log = tr.ytdlp_options()["logger"]

    log.debug("[youtube] Extracting URL")
    log.warning("No supported JavaScript runtime could be found")

    assert "Extracting URL" in caplog.text
    assert "JavaScript runtime" in caplog.text


def test_missing_ytdlp_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)

    with pytest.raises(tr.FallbackMissing, match=r"add the ytdlp extra"):
        tr.fetch_with_ytdlp(VIDEO_ID, ["vi"])


# --- fallback between the backends ---------------------------------------------------


def _backends(primary, fallback=None):
    return tr.TranscriptBackends(primary=primary, fallback=fallback)


def _raises(exc):
    def backend(video_id, languages):
        raise exc

    return backend


def _serves(source):
    calls = []

    def backend(video_id, languages):
        calls.append((video_id, list(languages)))
        return _transcript(source)

    backend.calls = calls
    return backend


@pytest.mark.parametrize("failure", [IpBlocked(VIDEO_ID), RuntimeError("player changed")])
def test_blocked_or_unexpected_failures_fall_back_to_ytdlp(failure, capsys, caplog):
    fallback = _serves("yt-dlp")

    result = tr.get_transcript(
        VIDEO_ID, ["vi"], True, 50_000, _backends(_raises(failure), fallback)
    )

    assert result["source"] == "yt-dlp"
    assert fallback.calls == [(VIDEO_ID, ["vi"])]
    assert "trying yt-dlp" in caplog.text
    assert capsys.readouterr().out == ""


def test_definitive_answers_do_not_fall_back():
    fallback = _serves("yt-dlp")
    backends = _backends(_raises(tr.TranscriptUnavailable("disabled")), fallback)

    with pytest.raises(tr.TranscriptUnavailable):
        tr.get_transcript(VIDEO_ID, ["vi"], True, 50_000, backends)
    assert fallback.calls == []


def test_missing_fallback_reports_the_block_and_the_install_hint():
    missing = _raises(
        tr.FallbackMissing("The yt-dlp fallback is not installed; add the ytdlp extra.")
    )

    with pytest.raises(ToolError) as raised:
        tr.get_transcript(
            VIDEO_ID, ["vi"], True, 50_000, _backends(_raises(IpBlocked(VIDEO_ID)), missing)
        )

    message = str(raised.value)
    assert "YouTube blocked the transcript request from this IP (IpBlocked)" in message
    assert "add the ytdlp extra" in message


def test_both_backends_failing_reports_both():
    backends = _backends(_raises(RuntimeError("player changed")), _raises(ValueError("bad json")))

    with pytest.raises(ToolError, match=r"player changed.*yt-dlp failed too \(bad json\)"):
        tr.get_transcript(VIDEO_ID, ["vi"], True, 50_000, backends)


def test_no_fallback_configured():
    with pytest.raises(ToolError, match="youtube-transcript-api failed"):
        tr.get_transcript(VIDEO_ID, ["vi"], True, 50_000, _backends(_raises(RuntimeError("x"))))


# --- the result --------------------------------------------------------


def test_render_with_and_without_timestamps():
    with_ts = tr.render(VIDEO_ID, _transcript(), True, 50_000)
    plain = tr.render(VIDEO_ID, _transcript(), False, 50_000)

    assert with_ts["text"] == "[00:00] Xin chào\n[01:15] the end"
    assert plain["text"] == "Xin chào\nthe end"
    assert (with_ts["truncated"], with_ts["total_chars"]) == (False, len(with_ts["text"]))
    assert {
        key: with_ts[key] for key in ("language_code", "is_generated", "source", "segment_count")
    } == {
        "language_code": "vi",
        "is_generated": False,
        "source": "youtube-transcript-api",
        "segment_count": 2,
    }


def test_render_cuts_at_a_line_boundary():
    long = _transcript(texts=[f"line {n:04d}" for n in range(500)])

    result = tr.render(VIDEO_ID, long, False, 1_000)

    assert result["truncated"] is True
    assert result["total_chars"] == 500 * 9 + 499
    assert len(result["text"]) <= 1_000
    assert result["text"].endswith("line 0099")


async def test_tool_reports_the_backend(call_tool):
    result = await call_tool(
        "youtube_get_transcript",
        {"video_id_or_url": f"https://youtu.be/{VIDEO_ID}", "include_timestamps": False},
        transcripts=_backends(_raises(IpBlocked(VIDEO_ID)), _serves("yt-dlp")),
    )

    assert result.structured_content["source"] == "yt-dlp"
    assert result.structured_content["text"] == "Xin chào\nthe end"


async def test_tool_rejects_a_tiny_max_chars(call_tool):
    result = await call_tool(
        "youtube_get_transcript", {"video_id_or_url": VIDEO_ID, "max_chars": 10}
    )

    assert result.is_error
    assert "greater than or equal to 1000" in result.content[0].text
