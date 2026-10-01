"""The MCP server: tool definitions and their wiring to the Google APIs.

`build_server(settings, provider)` returns a configured FastMCP server. Tests
pass a fake provider; `serve` passes nothing and gets the Google one. Building
a server does no network work; the first tool call loads the token.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from vunm_youtube_mcp import __version__, analytics, studio, transcript
from vunm_youtube_mcp.config import Mode, Settings
from vunm_youtube_mcp.errors import google_api_errors
from vunm_youtube_mcp.services import GoogleServiceProvider, ServiceProvider

VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"

VideoId = Annotated[
    str, Field(pattern=VIDEO_ID_PATTERN, description="The 11-character YouTube video ID.")
]
ReportDate = Annotated[
    date | None,
    Field(description="A calendar day as YYYY-MM-DD, in Pacific Time as YouTube reports it."),
]
Dimension = Literal["day", "month", "country"]

CategoryId = Annotated[
    str | None,
    Field(pattern=r"^[0-9]+$", description="Numeric video category ID, e.g. 27 (Education)."),
]

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True
)

INSTRUCTIONS = {
    Mode.FULL: (
        "Tools for the YouTube channel authorized on this machine: channel statistics, "
        "analytics reports, uploads, video metadata, comments and transcripts. "
        "youtube_update_video previews by default: show the user the changes and "
        "warnings, and call it with dry_run=false only after they confirm. "
    ),
    Mode.READ_ONLY: (
        "Read-only tools for the YouTube channel authorized on this machine: channel "
        "statistics, analytics reports, uploads, video metadata, comments and "
        "transcripts. This server cannot change the channel. "
    ),
    Mode.PUBLIC: (
        "Tools for public YouTube data, read with an API key: video details, comments, "
        "transcripts and search. There is no access to a channel's private data. "
    ),
}
AUTH_INSTRUCTION = (
    "If a tool reports that authorization is needed, ask the user to run the command "
    "it names in a terminal; do not retry until they have."
)


def build_server(settings: Settings, provider: ServiceProvider | None = None) -> FastMCP:
    """A server for `settings`, reaching Google through `provider`."""
    provider = provider or GoogleServiceProvider(settings)
    mode = settings.mode
    server = FastMCP(
        name="vunm-youtube-mcp",
        instructions=INSTRUCTIONS[mode] + AUTH_INSTRUCTION,
        version=__version__,
    )
    uploads_cache: dict[str, str] = {}

    def uploads_playlist() -> str:
        if "id" not in uploads_cache:
            uploads_cache["id"] = studio.uploads_playlist_id(provider.data())
        return uploads_cache["id"]

    @server.tool(title="Channel statistics", annotations=READ)
    def youtube_channel_stats() -> dict[str, Any]:
        """Statistics and profile of the authorized channel: subscribers, total views,
        video count, custom URL and the uploads playlist. Quota: 1 unit."""
        with google_api_errors(mode):
            return studio.channel_overview(provider.data())

    @server.tool(title="Channel analytics report", annotations=READ)
    def youtube_analytics_report(
        start_date: ReportDate = None,
        end_date: ReportDate = None,
        dimensions: Annotated[
            Dimension | None,
            Field(description="Group rows by day, month or country; null for totals."),
        ] = "day",
    ) -> dict[str, Any]:
        """Channel metrics from YouTube Analytics: views, watch time, average view
        duration and percentage, subscribers gained and lost, likes, comments, shares.

        Defaults to the 28 days that end 2 days ago (Pacific Time; recent days fill
        in late). Month reports use the first day of each month for both dates.
        Uses YouTube Analytics API quota, not YouTube Data API quota."""
        start, end = analytics.resolve_window(start_date, end_date)
        with google_api_errors(mode):
            return analytics.channel_report(provider.analytics(), start, end, dimensions)

    @server.tool(title="Video analytics", annotations=READ)
    def youtube_video_analytics(
        video_id: VideoId,
        start_date: ReportDate = None,
        end_date: ReportDate = None,
    ) -> dict[str, Any]:
        """Totals for one video from YouTube Analytics: views, watch time, average view
        duration and percentage, likes and shares.

        Defaults to the 28 days that end 2 days ago (Pacific Time)."""
        start, end = analytics.resolve_window(start_date, end_date)
        with google_api_errors(mode):
            return analytics.video_report(provider.analytics(), video_id, start, end)

    @server.tool(title="List channel uploads", annotations=READ)
    def youtube_list_videos(
        max_results: Annotated[int, Field(ge=1, le=50, description="Videos per page.")] = 10,
        page_token: Annotated[
            str | None, Field(description="next_page_token from the previous page.")
        ] = None,
    ) -> dict[str, Any]:
        """Uploads of the authorized channel, newest first, including private and
        unlisted videos, with view, like and comment counts. Returns
        {videos, next_page_token}; pass next_page_token to get the next page.
        Quota: 2 units a page (plus 1 on the first call)."""
        with google_api_errors(mode):
            return studio.list_videos(provider.data(), uploads_playlist(), max_results, page_token)

    @server.tool(title="Video details", annotations=READ)
    def youtube_get_video(video_id: VideoId) -> dict[str, Any]:
        """Metadata and settings of a video: title, full description, tags, category,
        privacy status, duration and statistics. Quota: 1 unit."""
        with google_api_errors(mode):
            return studio.video_details(provider.data(), video_id)

    @server.tool(title="Video transcript", annotations=READ)
    def youtube_get_transcript(
        video_id_or_url: Annotated[
            str, Field(description="A video ID or a YouTube URL (watch, youtu.be, shorts).")
        ],
        languages: Annotated[
            list[str] | None,
            Field(description="Language codes in order of preference; default vi, en."),
        ] = None,
        include_timestamps: bool = True,
    ) -> dict[str, Any]:
        """The transcript of a public video, from its caption tracks. Uses no YouTube
        Data API quota and needs no authorization."""
        return transcript.get_video_transcript(
            video_id_or_url, languages or ["vi", "en"], include_timestamps
        )

    @server.tool(title="Video comments", annotations=READ)
    def youtube_get_comments(
        video_id: VideoId,
        max_results: Annotated[int, Field(ge=1, le=100, description="Comments to return.")] = 20,
    ) -> list[dict[str, Any]]:
        """Top-level comments on a video, most relevant first, as plain text, with like
        and reply counts. Quota: 1 unit."""
        with google_api_errors(mode):
            return studio.video_comments(provider.data(), video_id, max_results)

    if mode is Mode.FULL:

        @server.tool(title="Update video metadata", annotations=WRITE)
        def youtube_update_video(
            video_id: VideoId,
            title: Annotated[
                str | None, Field(description="New title: up to 100 characters, no < or >.")
            ] = None,
            description: Annotated[
                str | None,
                Field(description="New description: up to 5000 bytes (UTF-8), no < or >."),
            ] = None,
            tags: Annotated[
                list[str] | None,
                Field(
                    description="Replaces every tag. Up to 500 characters in total, where "
                    "commas count and a tag with a space counts as quoted."
                ),
            ] = None,
            category_id: CategoryId = None,
            privacy_status: Literal["public", "unlisted", "private"] | None = None,
            dry_run: Annotated[
                bool, Field(description="Preview only (the default); false writes the change.")
            ] = True,
        ) -> dict[str, Any]:
            """Preview or apply a change to a video's title, description, tags,
            category or privacy status. Fields left out keep their values.

            With dry_run=true (the default) nothing is written: the result lists
            `changes` (before and after), `warnings` (for example, the video becoming
            public or tags being dropped) and `quota_cost`, the 50 units the write would
            cost. Show these to the user and call again with dry_run=false only after
            they confirm. Returns {changed: false} when nothing would change. A preview
            costs 1 quota unit; applying costs 51."""
            requested = {
                "title": title,
                "description": description,
                "tags": tags,
                "category_id": category_id,
                "privacy_status": privacy_status,
            }
            with google_api_errors(mode):
                return studio.update_video(provider.data(), video_id, requested, dry_run=dry_run)

    return server


_default_server: FastMCP | None = None


def __getattr__(name: str) -> Any:
    """`mcp`: the server configured from the environment, built on first access."""
    global _default_server
    if name == "mcp":
        if _default_server is None:
            _default_server = build_server(Settings.from_env())
        return _default_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
