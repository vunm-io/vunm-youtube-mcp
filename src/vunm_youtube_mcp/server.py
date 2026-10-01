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
from vunm_youtube_mcp.config import Settings
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

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)

INSTRUCTIONS = (
    "Tools for the YouTube channel authorized on this machine: channel statistics, "
    "analytics reports, uploads, video metadata, comments and transcripts. "
    "If a tool reports that authorization is needed, ask the user to run the "
    "command it names in a terminal; do not retry until they have."
)


def build_server(settings: Settings, provider: ServiceProvider | None = None) -> FastMCP:
    """A server for `settings`, reaching Google through `provider`."""
    provider = provider or GoogleServiceProvider(settings)
    mode = settings.mode
    server = FastMCP(name="vunm-youtube-mcp", instructions=INSTRUCTIONS, version=__version__)
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

    @server.tool(title="Update video metadata")
    def youtube_update_video(
        video_id: VideoId,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        category_id: str | None = None,
        privacy_status: Literal["public", "unlisted", "private"] | None = None,
    ) -> dict[str, Any]:
        """Change the title, description, tags, category or privacy status of a video.
        Fields left out keep their current values; tags replace the whole list.
        Quota: 51 units."""
        with google_api_errors(mode):
            return studio.update_video_metadata(
                provider.data(), video_id, title, description, tags, category_id, privacy_status
            )

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
