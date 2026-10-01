"""Video search through the YouTube Data API's search.list.

search.list draws on its own quota bucket: 100 calls a day per Google Cloud
project, and each page is one call. Listing the authorized channel's own
uploads is cheaper through the uploads playlist (`studio.list_videos`).
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

SEARCH_ORDERS = ("relevance", "date", "viewCount", "rating", "title")


def rfc3339(value: datetime) -> str:
    """`value` in UTC as search.list expects it; a naive datetime is taken as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def search_videos(
    youtube: Any,
    query: str,
    max_results: int,
    channel_id: str | None,
    order: str,
    published_after: datetime | None,
    page_token: str | None,
) -> dict[str, Any]:
    """One page of videos matching `query`. Cost: 1 call of the search bucket."""
    request: dict[str, Any] = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "order": order,
    }
    if channel_id:
        request["channelId"] = channel_id
    if published_after:
        request["publishedAfter"] = rfc3339(published_after)
    if page_token:
        request["pageToken"] = page_token
    response = youtube.search().list(**request).execute()

    videos = []
    for item in response.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        # search.list returns HTML-escaped text (&amp;, &#39;); the other endpoints do not.
        videos.append(
            {
                "video_id": video_id,
                "title": html.unescape(snippet.get("title") or ""),
                "description": html.unescape(snippet.get("description") or ""),
                "channel_id": snippet.get("channelId"),
                "channel_title": html.unescape(snippet.get("channelTitle") or ""),
                "published_at": snippet.get("publishedAt"),
                "live_broadcast_content": snippet.get("liveBroadcastContent"),
                "thumbnails": snippet.get("thumbnails", {}),
            }
        )
    return {
        "videos": videos,
        "next_page_token": response.get("nextPageToken"),
        "total_results": response.get("pageInfo", {}).get("totalResults"),
    }
