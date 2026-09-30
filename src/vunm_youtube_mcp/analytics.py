"""YouTube Analytics API v2 reporting module.

Fetches key channel and video performance metrics such as views, watch time,
retention, and subscriber gains/losses across specified date ranges.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from .auth import get_youtube_analytics_service


def get_channel_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    dimensions: Optional[str] = "day",
) -> Dict[str, Any]:
    """Query YouTube Analytics reports for the authenticated channel.
    
    Args:
        start_date: Format 'YYYY-MM-DD'. Defaults to 28 days ago.
        end_date: Format 'YYYY-MM-DD'. Defaults to yesterday (YouTube analytics has a 2-day lag).
        dimensions: Aggregation dimension (e.g. 'day', 'month', 'country', or None).
    """
    analytics = get_youtube_analytics_service()

    # Default to past 28 days ending 2 days ago (lag in data availability)
    today = datetime.utcnow().date()
    if not end_date:
        end_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    if not start_date:
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,subscribersGained,subscribersLost,likes,comments"
    )

    request_kwargs: Dict[str, Any] = {
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": metrics,
    }

    if dimensions:
        request_kwargs["dimensions"] = dimensions
        if dimensions == "day":
            request_kwargs["sort"] = "day"

    try:
        response = analytics.reports().query(**request_kwargs).execute()
    except Exception as e:
        return {"error": f"Analytics query failed: {e}"}

    column_headers = [header.get("name") for header in response.get("columnHeaders", [])]
    rows = response.get("rows", [])

    formatted_rows = []
    for row in rows:
        formatted_rows.append(dict(zip(column_headers, row)))

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_records": len(rows),
        "columns": column_headers,
        "data": formatted_rows,
    }


def get_video_analytics(
    video_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Query specific performance analytics for a single video.
    
    Args:
        video_id: The 11-character YouTube video ID.
        start_date: Format 'YYYY-MM-DD'. Defaults to 28 days ago.
        end_date: Format 'YYYY-MM-DD'. Defaults to 2 days ago.
    """
    analytics = get_youtube_analytics_service()

    today = datetime.utcnow().date()
    if not end_date:
        end_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    if not start_date:
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,likes,shares"
    )

    try:
        response = analytics.reports().query(
            ids="channel==MINE",
            filters=f"video=={video_id}",
            startDate=start_date,
            endDate=end_date,
            metrics=metrics,
        ).execute()
    except Exception as e:
        return {"error": f"Video analytics query failed: {e}"}

    column_headers = [header.get("name") for header in response.get("columnHeaders", [])]
    rows = response.get("rows", [])

    formatted_rows = []
    for row in rows:
        formatted_rows.append(dict(zip(column_headers, row)))

    return {
        "video_id": video_id,
        "start_date": start_date,
        "end_date": end_date,
        "data": formatted_rows[0] if formatted_rows else {},
    }
