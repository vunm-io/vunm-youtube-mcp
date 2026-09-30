"""Custom YouTube Model Context Protocol (MCP) Server.

Exposes a comprehensive suite of tools for YouTube Channel Analytics,
YouTube Studio Video Management, Transcript Extraction, and Comment Handling.
"""

from typing import Any

from fastmcp import FastMCP

from .analytics import get_channel_analytics, get_video_analytics
from .studio import (
    get_channel_overview,
    get_video_comments,
    get_video_details,
    list_recent_videos,
    update_video_metadata,
)
from .transcript import get_video_transcript

# Initialize FastMCP Server
mcp = FastMCP(
    name="YouTube Management MCP",
    instructions=(
        "You are connected to a Custom YouTube MCP Server with authenticated access to the user's YouTube channel. "
        "You can inspect channel metrics, fetch deep analytics reports, browse uploads, edit video metadata, "
        "read comments, and extract transcripts for video summarization."
    ),
)


@mcp.tool()
def youtube_channel_stats() -> dict[str, Any]:
    """Retrieve high-level statistics and metadata for the authenticated YouTube channel.

    Returns subscriber count, total view count, video count, and channel profile information.
    """
    return get_channel_overview()


@mcp.tool()
def youtube_analytics_report(
    start_date: str | None = None,
    end_date: str | None = None,
    dimensions: str | None = "day",
) -> dict[str, Any]:
    """Fetch performance analytics reports for the channel via YouTube Analytics API.

    Args:
        start_date: Start date in 'YYYY-MM-DD' format (e.g. '2026-08-01'). Defaults to 30 days ago.
        end_date: End date in 'YYYY-MM-DD' format. Defaults to 2 days ago (due to YouTube API reporting lag).
        dimensions: Dimension to group by, such as 'day', 'month', or None for overall total.
    """
    return get_channel_analytics(
        start_date=start_date or None,
        end_date=end_date or None,
        dimensions=dimensions or "day",
    )


@mcp.tool()
def youtube_video_analytics(
    video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Fetch deep performance analytics for a single video (views, watch time, retention, shares).

    Args:
        video_id: The 11-character YouTube video ID.
        start_date: Start date in 'YYYY-MM-DD' format.
        end_date: End date in 'YYYY-MM-DD' format.
    """
    return get_video_analytics(
        video_id=video_id,
        start_date=start_date or None,
        end_date=end_date or None,
    )


@mcp.tool()
def youtube_list_videos(max_results: int = 10) -> list[dict[str, Any]]:
    """List recent videos uploaded to the channel (including public, unlisted, and private videos).

    Args:
        max_results: Number of recent videos to retrieve (between 1 and 50).
    """
    return list_recent_videos(max_results=max_results)


@mcp.tool()
def youtube_get_video(video_id: str) -> dict[str, Any]:
    """Retrieve current metadata and settings for a specific video.

    Returns title, full description, list of tags, category ID, privacy status, and view/like stats.
    """
    return get_video_details(video_id=video_id)


@mcp.tool()
def youtube_update_video(
    video_id: str,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    category_id: str | None = None,
    privacy_status: str | None = None,
) -> dict[str, Any]:
    """Update title, description, tags, category, and/or privacy status for a video on YouTube Studio.

    Only provide the fields you wish to modify. Unspecified fields will retain their existing values.

    Args:
        video_id: The 11-character YouTube video ID to edit.
        title: New video title.
        description: New video description.
        tags: Complete replacement list of video tags/keywords.
        category_id: Numeric YouTube video category ID (e.g. '27' for Education, '28' for Science & Tech).
        privacy_status: One of 'public', 'unlisted', or 'private'.
    """
    return update_video_metadata(
        video_id=video_id,
        title=title,
        description=description,
        tags=tags,
        category_id=category_id,
        privacy_status=privacy_status,
    )


@mcp.tool()
def youtube_get_transcript(
    video_id_or_url: str,
    languages: list[str] | None = None,
    include_timestamps: bool = True,
) -> dict[str, Any]:
    """Extract subtitles/transcript from a YouTube video for AI summarization and content analysis.

    Args:
        video_id_or_url: YouTube URL (e.g. 'https://www.youtube.com/watch?v=...' or 11-character ID).
        languages: Preferred language codes in order of priority (default: ['vi', 'en']).
        include_timestamps: Whether to prefix lines with timestamps [MM:SS].
    """
    return get_video_transcript(
        video_id_or_url=video_id_or_url,
        languages=languages or ["vi", "en"],
        include_timestamps=include_timestamps,
    )


@mcp.tool()
def youtube_get_comments(video_id: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Retrieve top comments on a video for sentiment evaluation or drafting responses.

    Args:
        video_id: The 11-character YouTube video ID.
        max_results: Maximum comments to retrieve (default: 20).
    """
    return get_video_comments(video_id=video_id, max_results=max_results)


if __name__ == "__main__":
    mcp.run()
