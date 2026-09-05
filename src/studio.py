"""YouTube Studio & Data API v3 management module.

Handles channel statistics, listing channel videos efficiently (using playlistItems
to conserve quota), retrieving video details, updating metadata, and reading comments.
"""

from typing import Any, Dict, List, Optional
from .auth import get_youtube_data_service


def get_channel_overview() -> Dict[str, Any]:
    """Retrieve high-level statistics and metadata for the authenticated channel."""
    youtube = get_youtube_data_service()
    response = youtube.channels().list(
        mine=True,
        part="snippet,contentDetails,statistics"
    ).execute()

    items = response.get("items", [])
    if not items:
        return {"error": "No channel found for the authenticated account."}

    channel = items[0]
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


def list_recent_videos(max_results: int = 10) -> List[Dict[str, Any]]:
    """List recent videos uploaded to the channel (including unlisted/private).
    
    Uses uploads playlist to conserve API quota (1 unit vs 100 units for search).
    """
    youtube = get_youtube_data_service()
    
    # Get channel uploads playlist
    overview = get_channel_overview()
    if "error" in overview:
        return [{"error": overview["error"]}]
    
    uploads_id = overview.get("uploads_playlist_id")
    if not uploads_id:
        return [{"error": "Could not locate uploads playlist ID."}]

    # Fetch playlist items
    playlist_resp = youtube.playlistItems().list(
        playlistId=uploads_id,
        part="snippet,status,contentDetails",
        maxResults=min(max(1, max_results), 50)
    ).execute()

    items = playlist_resp.get("items", [])
    if not items:
        return []

    video_ids = [item["contentDetails"]["videoId"] for item in items if "contentDetails" in item]

    # Fetch video statistics
    stats_map = {}
    if video_ids:
        videos_resp = youtube.videos().list(
            id=",".join(video_ids),
            part="statistics,status"
        ).execute()
        for v in videos_resp.get("items", []):
            stats_map[v["id"]] = {
                "statistics": v.get("statistics", {}),
                "privacy_status": v.get("status", {}).get("privacyStatus"),
            }

    results = []
    for item in items:
        snippet = item.get("snippet", {})
        vid = item.get("contentDetails", {}).get("videoId")
        v_info = stats_map.get(vid, {})
        v_stats = v_info.get("statistics", {})

        results.append({
            "video_id": vid,
            "title": snippet.get("title"),
            "published_at": snippet.get("publishedAt"),
            "privacy_status": v_info.get("privacy_status", item.get("status", {}).get("privacyStatus")),
            "view_count": v_stats.get("viewCount", "0"),
            "like_count": v_stats.get("likeCount", "0"),
            "comment_count": v_stats.get("commentCount", "0"),
            "thumbnails": snippet.get("thumbnails", {}),
        })

    return results


def get_video_details(video_id: str) -> Dict[str, Any]:
    """Retrieve full details, snippet, tags, category, and statistics for a specific video."""
    youtube = get_youtube_data_service()
    response = youtube.videos().list(
        id=video_id,
        part="snippet,status,statistics,contentDetails"
    ).execute()

    items = response.get("items", [])
    if not items:
        return {"error": f"Video '{video_id}' not found."}

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
    video_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category_id: Optional[str] = None,
    privacy_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Update title, description, tags, category, and/or privacy status of a video.
    
    Fetches existing snippet first to preserve unmodified fields and satisfy
    mandatory YouTube API parameters.
    """
    youtube = get_youtube_data_service()

    # Step 1: Fetch existing data
    get_resp = youtube.videos().list(
        id=video_id,
        part="snippet,status"
    ).execute()

    items = get_resp.get("items", [])
    if not items:
        return {"error": f"Video '{video_id}' not found."}

    existing_video = items[0]
    snippet = existing_video.get("snippet", {})
    status = existing_video.get("status", {})

    # Step 2: Apply updates
    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description
    if tags is not None:
        snippet["tags"] = tags
    if category_id is not None:
        snippet["categoryId"] = category_id
    if privacy_status is not None:
        valid_statuses = ["public", "private", "unlisted"]
        if privacy_status.lower() in valid_statuses:
            status["privacyStatus"] = privacy_status.lower()
        else:
            return {"error": f"Invalid privacy_status '{privacy_status}'. Must be one of {valid_statuses}."}

    # Step 3: Execute update
    update_body = {
        "id": video_id,
        "snippet": snippet,
        "status": status,
    }

    update_resp = youtube.videos().update(
        part="snippet,status",
        body=update_body
    ).execute()

    updated_snippet = update_resp.get("snippet", {})
    updated_status = update_resp.get("status", {})

    return {
        "success": True,
        "video_id": update_resp.get("id"),
        "title": updated_snippet.get("title"),
        "description": updated_snippet.get("description"),
        "tags": updated_snippet.get("tags", []),
        "category_id": updated_snippet.get("categoryId"),
        "privacy_status": updated_status.get("privacyStatus"),
    }


def get_video_comments(video_id: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """Retrieve top recent comments for a video."""
    youtube = get_youtube_data_service()
    try:
        response = youtube.commentThreads().list(
            videoId=video_id,
            part="snippet",
            maxResults=min(max(1, max_results), 100),
            order="relevance"
        ).execute()
    except Exception as e:
        return [{"error": f"Failed to fetch comments: {e}"}]

    comments = []
    for item in response.get("items", []):
        top_comment = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
        comments.append({
            "comment_id": item.get("id"),
            "author": top_comment.get("authorDisplayName"),
            "text": top_comment.get("textDisplay"),
            "like_count": top_comment.get("likeCount", 0),
            "published_at": top_comment.get("publishedAt"),
            "total_reply_count": item.get("snippet", {}).get("totalReplyCount", 0),
        })

    return comments
