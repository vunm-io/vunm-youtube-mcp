"""Live smoke test against a real channel. Not run in CI.

Calls every tool through the MCP client against the real Google APIs and
prints one PASS, FAIL or SKIP line per check. It never prints channel data
(titles, IDs, counts); `--verbose` adds error messages to FAIL lines, for your
own terminal only.

    uv run vunm-youtube-mcp auth                        # once
    uv run python scripts/live_smoke.py                 # read tools, search, transcripts
    uv run python scripts/live_smoke.py --preview-video VIDEO_ID
    uv run python scripts/live_smoke.py --write-video VIDEO_ID   # a PRIVATE test video
    YOUTUBE_API_KEY=... uv run python scripts/live_smoke.py --public

`--write-video` really writes: it adds a tag to the video and then restores
its tags (about 103 quota units). It refuses a video that is not private.
The exit code is 1 when a check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp import Client
from youtube_transcript_api import RequestBlocked

from vunm_youtube_mcp import auth, transcript
from vunm_youtube_mcp.config import Settings
from vunm_youtube_mcp.server import build_server

PUBLIC_VIDEO = "jNQXAC9IVRw"  # "Me at the zoo": public, short, with English captions
SMOKE_TAG = "vymcp-smoke"


class Smoke:
    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}

    def report(self, status: str, name: str, detail: str = "") -> None:
        self.counts[status] += 1
        print(f"{status}  {name}{f' ({detail})' if detail else ''}")

    async def check(self, name: str, run: Callable[[], Awaitable[str | None]]) -> None:
        try:
            note = await run()
        except Exception as exc:  # noqa: BLE001 - a smoke test reports every failure
            detail = type(exc).__name__ + (f": {exc}" if self.verbose else "")
            self.report("FAIL", name, detail)
        else:
            self.report("PASS", name, note or "")

    def skip(self, name: str, why: str) -> None:
        self.report("SKIP", name, why)


async def call(client: Client, tool: str, arguments: dict[str, Any] | None = None) -> Any:
    result = await client.call_tool(tool, arguments or {})
    return result.structured_content


def _blocked(video_id: str, languages) -> transcript.Transcript:
    raise RequestBlocked(video_id)


async def oauth_checks(smoke: Smoke, args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    state: dict[str, Any] = {}

    async with Client(build_server(settings)) as client:

        async def stats():
            assert (await call(client, "youtube_channel_stats"))["channel_id"]

        async def uploads():
            page = await call(client, "youtube_list_videos", {"max_results": 5})
            assert isinstance(page["videos"], list)
            if page["videos"]:
                state["video"] = page["videos"][0]["video_id"]
            state["next"] = page["next_page_token"]
            return f"{len(page['videos'])} on the first page"

        async def next_page():
            page = await call(
                client, "youtube_list_videos", {"max_results": 5, "page_token": state["next"]}
            )
            assert isinstance(page["videos"], list)

        await smoke.check("youtube_channel_stats", stats)
        await smoke.check("youtube_list_videos", uploads)
        if state.get("next"):
            await smoke.check("youtube_list_videos (page 2)", next_page)
        else:
            smoke.skip("youtube_list_videos (page 2)", "one page only")

        video = args.preview_video or state.get("video")
        if video:

            async def details():
                assert (await call(client, "youtube_get_video", {"video_id": video}))["video_id"]

            async def comments():
                result = await client.call_tool(
                    "youtube_get_comments", {"video_id": video}, raise_on_error=False
                )
                if result.is_error and "Comments are disabled" in result.content[0].text:
                    return "comments disabled"
                assert not result.is_error, result.content[0].text
                return None

            async def video_report():
                report = await call(client, "youtube_video_analytics", {"video_id": video})
                assert "metrics" in report

            await smoke.check("youtube_get_video", details)
            await smoke.check("youtube_get_comments", comments)
            await smoke.check("youtube_video_analytics", video_report)
        else:
            for name in ("youtube_get_video", "youtube_get_comments", "youtube_video_analytics"):
                smoke.skip(name, "the channel has no uploads; pass --preview-video")

        for dimension in ("day", "month", "country", None):

            async def channel_report(dimension=dimension):
                report = await call(client, "youtube_analytics_report", {"dimensions": dimension})
                assert isinstance(report["rows"], list)

            await smoke.check(f"youtube_analytics_report ({dimension or 'totals'})", channel_report)

        async def search():
            found = await call(client, "youtube_search_videos", {"query": "YouTube Data API"})
            assert isinstance(found["videos"], list)

        await smoke.check("youtube_search_videos", search)

        if args.preview_video:

            async def preview():
                current = await call(client, "youtube_get_video", {"video_id": args.preview_video})
                result = await call(
                    client,
                    "youtube_update_video",
                    {"video_id": args.preview_video, "tags": [*current["tags"], SMOKE_TAG]},
                )
                assert result["dry_run"] is True and "tags" in result["changes"]

            await smoke.check("youtube_update_video (preview)", preview)
        else:
            smoke.skip("youtube_update_video (preview)", "pass --preview-video")

        if args.write_video:

            async def write():
                current = await call(client, "youtube_get_video", {"video_id": args.write_video})
                if current["privacy_status"] != "private":
                    raise RuntimeError("refusing to write: the video is not private")
                tags = current["tags"]
                added = await call(
                    client,
                    "youtube_update_video",
                    {"video_id": args.write_video, "tags": [*tags, SMOKE_TAG], "dry_run": False},
                )
                assert SMOKE_TAG in added["applied"]["tags"]
                restored = await call(
                    client,
                    "youtube_update_video",
                    {"video_id": args.write_video, "tags": tags, "dry_run": False},
                )
                assert restored["applied"]["tags"] == tags
                return "tag added, then the tags restored"

            await smoke.check("youtube_update_video (write)", write)
        else:
            smoke.skip("youtube_update_video (write)", "pass --write-video with a private video")

    async def read_only_refuses_full_token():
        try:
            auth.load_credentials(
                Settings.from_env({**os.environ, "YOUTUBE_MCP_MODE": "read-only"})
            )
        except auth.AuthRequired as exc:
            assert "read-only mode needs" in str(exc), "expected a scope mismatch"
            return
        raise AssertionError("read-only mode accepted a token with other scopes")

    await smoke.check("read-only mode refuses a full-mode token", read_only_refuses_full_token)


async def transcript_checks(smoke: Smoke) -> None:
    settings = Settings.from_env()
    forced = transcript.TranscriptBackends(primary=_blocked, fallback=transcript.fetch_with_ytdlp)
    for name, backends, source in (
        ("youtube_get_transcript", None, "youtube-transcript-api"),
        ("youtube_get_transcript (forced yt-dlp fallback)", forced, "yt-dlp"),
    ):
        async with Client(build_server(settings, transcripts=backends)) as client:

            async def fetch(client=client, source=source):
                result = await call(
                    client, "youtube_get_transcript", {"video_id_or_url": PUBLIC_VIDEO}
                )
                assert result["source"] == source and result["segment_count"] > 0

            await smoke.check(name, fetch)


async def public_checks(smoke: Smoke) -> None:
    settings = Settings.from_env({**os.environ, "YOUTUBE_MCP_MODE": "public"})
    if not settings.api_key:
        for name in ("get_video", "get_comments", "search_videos", "get_transcript"):
            smoke.skip(f"public: youtube_{name}", "set YOUTUBE_API_KEY")
        return
    async with Client(build_server(settings)) as client:
        tools = {tool.name for tool in await client.list_tools()}

        async def listed():
            assert len(tools) == 4, sorted(tools)

        async def get_video():
            assert (await call(client, "youtube_get_video", {"video_id": PUBLIC_VIDEO}))["video_id"]

        async def comments():
            assert isinstance(
                (await call(client, "youtube_get_comments", {"video_id": PUBLIC_VIDEO}))["result"],
                list,
            )

        async def search():
            found = await call(client, "youtube_search_videos", {"query": "YouTube Data API"})
            assert isinstance(found["videos"], list)

        async def fetch():
            result = await call(client, "youtube_get_transcript", {"video_id_or_url": PUBLIC_VIDEO})
            assert result["segment_count"] > 0

        await smoke.check("public: lists 4 tools", listed)
        await smoke.check("public: youtube_get_video", get_video)
        await smoke.check("public: youtube_get_comments", comments)
        await smoke.check("public: youtube_search_videos", search)
        await smoke.check("public: youtube_get_transcript", fetch)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview-video", help="a video of yours to preview an update on")
    parser.add_argument("--write-video", help="a PRIVATE test video to really write to")
    parser.add_argument("--public", action="store_true", help="also check public mode")
    parser.add_argument("--verbose", action="store_true", help="show error messages")
    args = parser.parse_args(argv)

    smoke = Smoke(args.verbose)
    await oauth_checks(smoke, args)
    await transcript_checks(smoke)
    if args.public:
        await public_checks(smoke)

    counts = smoke.counts
    print(f"{counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
