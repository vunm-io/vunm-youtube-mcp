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


# Limits from the videos resource reference (developers.google.com/youtube/v3/docs/videos).
TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_CHARS = 500
UPDATE_QUOTA_COST = 50

# Mutable properties of the parts videos.update writes. The API resets every
# mutable property of a part it writes that the body leaves out, so the body
# carries all of them, and only parts that change are written.
SNIPPET_WRITABLE = (
    "title",
    "description",
    "tags",
    "categoryId",
    "defaultLanguage",
    "defaultAudioLanguage",
)
STATUS_WRITABLE = (
    "privacyStatus",
    "publishAt",
    "license",
    "embeddable",
    "publicStatsViewable",
    "selfDeclaredMadeForKids",
    "containsSyntheticMedia",
)
# Tool argument -> (part, property).
UPDATABLE = {
    "title": ("snippet", "title"),
    "description": ("snippet", "description"),
    "tags": ("snippet", "tags"),
    "category_id": ("snippet", "categoryId"),
    "privacy_status": ("status", "privacyStatus"),
}


def tags_length(tags: list[str]) -> int:
    """Length of a tag list as YouTube counts it: commas count, and a tag with a
    space counts as if it were quoted."""
    quoted = sum(len(tag) + 2 if " " in tag else len(tag) for tag in tags)
    return quoted + max(len(tags) - 1, 0)


def validate_metadata(title: str | None, description: str | None, tags: list[str] | None) -> None:
    """Reject values the API would refuse, before any request is made."""
    if title is not None:
        if not title.strip():
            raise ToolError("title cannot be empty.")
        if len(title) > TITLE_MAX_CHARS:
            raise ToolError(f"title has {len(title)} characters; the limit is {TITLE_MAX_CHARS}.")
        if "<" in title or ">" in title:
            raise ToolError("title cannot contain < or >.")
    if description is not None:
        size = len(description.encode("utf-8"))
        if size > DESCRIPTION_MAX_BYTES:
            raise ToolError(
                f"description is {size} bytes in UTF-8; the limit is {DESCRIPTION_MAX_BYTES}."
            )
        if "<" in description or ">" in description:
            raise ToolError("description cannot contain < or >.")
    if tags is not None:
        if any(not tag.strip() for tag in tags):
            raise ToolError("tags cannot contain an empty tag.")
        length = tags_length(tags)
        if length > TAGS_MAX_CHARS:
            raise ToolError(
                f"tags add up to {length} characters as YouTube counts them (commas count, "
                f"tags with spaces count as quoted); the limit is {TAGS_MAX_CHARS}."
            )


def update_video(
    youtube: Any,
    video_id: str,
    requested: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Preview, or apply, a change to a video's metadata.

    `requested` maps tool arguments (title, description, tags, category_id,
    privacy_status) to new values; None means keep. Returns `{changed: false}`
    when nothing would change, the diff and warnings for a dry run, and the
    updated values after a write.
    """
    requested = {name: value for name, value in requested.items() if value is not None}
    validate_metadata(requested.get("title"), requested.get("description"), requested.get("tags"))

    items = youtube.videos().list(id=video_id, part="snippet,status").execute().get("items", [])
    if not items:
        raise ToolError(f"Video {video_id} was not found, or this account cannot see it.")
    current = {"snippet": items[0].get("snippet", {}), "status": items[0].get("status", {})}

    changes: dict[str, dict[str, Any]] = {}
    for name, value in requested.items():
        part, prop = UPDATABLE[name]
        before = current[part].get(prop, [] if prop == "tags" else None)
        if before != value:
            changes[name] = {"before": before, "after": value}
    if not changes:
        return {"changed": False, "video_id": video_id}

    warnings = []
    privacy = changes.get("privacy_status")
    if privacy and privacy["after"] == "public":
        warnings.append("The video becomes public: anyone can find and watch it.")
    publish_at = current["status"].get("publishAt")
    if privacy and privacy["after"] != "private" and publish_at:
        warnings.append(f"The scheduled publish time ({publish_at}) is cleared.")
    if "tags" in changes:
        kept = set(changes["tags"]["after"])
        dropped = [tag for tag in changes["tags"]["before"] if tag not in kept]
        if dropped:
            warnings.append(f"Replacing the tags drops {len(dropped)} existing tag(s): {dropped}.")

    if dry_run:
        return {
            "dry_run": True,
            "video_id": video_id,
            "changes": changes,
            "warnings": warnings,
            "quota_cost": UPDATE_QUOTA_COST,
        }

    body: dict[str, Any] = {"id": video_id}
    parts = sorted({UPDATABLE[name][0] for name in changes})
    for part in parts:
        writable = SNIPPET_WRITABLE if part == "snippet" else STATUS_WRITABLE
        body[part] = {key: current[part][key] for key in writable if key in current[part]}
    for name in changes:
        part, prop = UPDATABLE[name]
        body[part][prop] = changes[name]["after"]
    if "status" in body and body["status"].get("privacyStatus") != "private":
        body["status"].pop("publishAt", None)

    updated = youtube.videos().update(part=",".join(parts), body=body).execute()
    applied = {}
    for name in changes:
        part, prop = UPDATABLE[name]
        applied[name] = updated.get(part, {}).get(prop)
    return {
        "dry_run": False,
        "video_id": video_id,
        "changes": changes,
        "warnings": warnings,
        "applied": applied,
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
