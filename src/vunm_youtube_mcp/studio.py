"""Channel, video and comment reads through the YouTube Data API v3.

Every function takes the API client (a googleapiclient ``Resource``) as its
first argument and raises `ToolError` for an empty result. Quota cost per call
is noted in each docstring (units from Google's quota table).
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError


def _own_channel(youtube: Any, part: str) -> dict[str, Any]:
    items = youtube.channels().list(mine=True, part=part).execute().get("items", [])
    if not items:
        raise ToolError("The authorized Google account has no YouTube channel.")
    return items[0]


def channel_overview(youtube: Any) -> dict[str, Any]:
    """Statistics and profile of the authorized channel. Cost: 1 unit."""
    channel = _own_channel(youtube, "snippet,contentDetails,statistics")
    snippet = channel.get("snippet", {})
    stats = channel.get("statistics", {})
    content = channel.get("contentDetails", {})
    return {
        "channel_id": channel.get("id"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "custom_url": snippet.get("customUrl"),
        "published_at": snippet.get("publishedAt"),
        "subscriber_count": stats.get("subscriberCount"),
        "total_views": stats.get("viewCount"),
        "video_count": stats.get("videoCount"),
        "hidden_subscriber_count": stats.get("hiddenSubscriberCount"),
        "uploads_playlist_id": content.get("relatedPlaylists", {}).get("uploads"),
    }


def uploads_playlist_id(youtube: Any) -> str:
    """The playlist that holds every upload of the authorized channel. Cost: 1 unit."""
    channel = _own_channel(youtube, "contentDetails")
    playlist_id = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not playlist_id:
        raise ToolError("YouTube returned no uploads playlist for the authorized channel.")
    return playlist_id


def list_videos(
    youtube: Any, playlist_id: str, max_results: int, page_token: str | None
) -> dict[str, Any]:
    """One page of uploads, newest first, with statistics. Cost: 2 units.

    Reads the uploads playlist (1 unit) instead of search.list, which draws on
    a separate bucket of only 100 calls a day, and includes private and
    unlisted videos, which search does not.
    """
    request: dict[str, Any] = {
        "playlistId": playlist_id,
        "part": "snippet,status,contentDetails",
        "maxResults": max_results,
    }
    if page_token:
        request["pageToken"] = page_token
    page = youtube.playlistItems().list(**request).execute()
    items = page.get("items", [])

    video_ids = [
        item["contentDetails"]["videoId"]
        for item in items
        if item.get("contentDetails", {}).get("videoId")
    ]
    details: dict[str, dict[str, Any]] = {}
    if video_ids:
        response = youtube.videos().list(id=",".join(video_ids), part="statistics,status").execute()
        details = {video["id"]: video for video in response.get("items", [])}

    videos = []
    for item in items:
        snippet = item.get("snippet", {})
        video_id = item.get("contentDetails", {}).get("videoId")
        video = details.get(video_id, {})
        stats = video.get("statistics", {})
        status = video.get("status") or item.get("status", {})
        videos.append(
            {
                "video_id": video_id,
                "title": snippet.get("title"),
                "published_at": snippet.get("publishedAt"),
                "privacy_status": status.get("privacyStatus"),
                "view_count": stats.get("viewCount"),
                "like_count": stats.get("likeCount"),
                "comment_count": stats.get("commentCount"),
                "thumbnails": snippet.get("thumbnails", {}),
            }
        )
    return {"videos": videos, "next_page_token": page.get("nextPageToken")}


def video_details(youtube: Any, video_id: str) -> dict[str, Any]:
    """Metadata, settings and statistics of one video. Cost: 1 unit."""
    response = (
        youtube.videos()
        .list(id=video_id, part="snippet,status,statistics,contentDetails")
        .execute()
    )
    items = response.get("items", [])
    if not items:
        raise ToolError(f"Video {video_id} was not found, or this account cannot see it.")
    video = items[0]
    snippet = video.get("snippet", {})
    status = video.get("status", {})
    stats = video.get("statistics", {})
    content = video.get("contentDetails", {})
    return {
        "video_id": video.get("id"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "tags": snippet.get("tags", []),
        "category_id": snippet.get("categoryId"),
        "default_language": snippet.get("defaultLanguage"),
        "privacy_status": status.get("privacyStatus"),
        "duration": content.get("duration"),
        "view_count": stats.get("viewCount"),
        "like_count": stats.get("likeCount"),
        "comment_count": stats.get("commentCount"),
        "published_at": snippet.get("publishedAt"),
    }


def update_video_metadata(
    youtube: Any,
    video_id: str,
    title: str | None,
    description: str | None,
    tags: list[str] | None,
    category_id: str | None,
    privacy_status: str | None,
) -> dict[str, Any]:
    """Change the given fields of a video, keeping the others. Cost: 51 units."""
    items = youtube.videos().list(id=video_id, part="snippet,status").execute().get("items", [])
    if not items:
        raise ToolError(f"Video {video_id} was not found, or this account cannot see it.")
    snippet = items[0].get("snippet", {})
    status = items[0].get("status", {})
    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description
    if tags is not None:
        snippet["tags"] = tags
    if category_id is not None:
        snippet["categoryId"] = category_id
    if privacy_status is not None:
        status["privacyStatus"] = privacy_status
    updated = (
        youtube.videos()
        .update(part="snippet,status", body={"id": video_id, "snippet": snippet, "status": status})
        .execute()
    )
    updated_snippet = updated.get("snippet", {})
    return {
        "video_id": updated.get("id"),
        "title": updated_snippet.get("title"),
        "description": updated_snippet.get("description"),
        "tags": updated_snippet.get("tags", []),
        "category_id": updated_snippet.get("categoryId"),
        "privacy_status": updated.get("status", {}).get("privacyStatus"),
    }


def video_comments(youtube: Any, video_id: str, max_results: int) -> list[dict[str, Any]]:
    """Top-level comments on a video, most relevant first. Cost: 1 unit."""
    response = (
        youtube.commentThreads()
        .list(
            videoId=video_id,
            part="snippet",
            maxResults=max_results,
            order="relevance",
            textFormat="plainText",
        )
        .execute()
    )
    comments = []
    for thread in response.get("items", []):
        thread_snippet = thread.get("snippet", {})
        comment = thread_snippet.get("topLevelComment", {}).get("snippet", {})
        comments.append(
            {
                "comment_id": thread.get("id"),
                "author": comment.get("authorDisplayName"),
                "text": comment.get("textDisplay"),
                "like_count": comment.get("likeCount", 0),
                "published_at": comment.get("publishedAt"),
                "total_reply_count": thread_snippet.get("totalReplyCount", 0),
            }
        )
    return comments
