"""Channel and video reports through the YouTube Analytics API v2.

YouTube Analytics dates are calendar days in Pacific Time, and the newest days
fill in with a lag, so the default window is the 28 days that end 2 days before
today in Pacific Time.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastmcp.exceptions import ToolError

REPORTING_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_WINDOW_DAYS = 28
REPORTING_LAG_DAYS = 2

CHANNEL_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "subscribersGained,subscribersLost,likes,comments,shares"
)
VIDEO_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,shares"
)
SORT_BY_DIMENSION = {"day": "day", "month": "month", "country": "-views"}


def reporting_today() -> date:
    """Today's date in Pacific Time, the time zone YouTube Analytics reports in."""
    return datetime.now(REPORTING_TZ).date()


def resolve_window(
    start_date: date | None, end_date: date | None, today: date | None = None
) -> tuple[date, date]:
    """Fill in the default window and check the order of the dates."""
    end = end_date or (today or reporting_today()) - timedelta(days=REPORTING_LAG_DAYS)
    start = start_date or end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if start > end:
        raise ToolError(f"start_date {start} is after end_date {end}.")
    return start, end


def _rows(response: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    columns = [header.get("name") for header in response.get("columnHeaders", [])]
    rows = [dict(zip(columns, row, strict=True)) for row in response.get("rows", [])]
    return columns, rows


def channel_report(analytics: Any, start: date, end: date, dimension: str | None) -> dict[str, Any]:
    """Channel metrics for [start, end], per day, month or country, or as totals.

    Month reports need both dates on the first of a month, so they are moved
    to the first of their months; the dates used are in the result.
    """
    if dimension == "month":
        start, end = start.replace(day=1), end.replace(day=1)
    query: dict[str, Any] = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": CHANNEL_METRICS,
    }
    if dimension:
        query["dimensions"] = dimension
        query["sort"] = SORT_BY_DIMENSION[dimension]
    columns, rows = _rows(analytics.reports().query(**query).execute())
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "dimension": dimension,
        "columns": columns,
        "rows": rows,
    }


def video_report(analytics: Any, video_id: str, start: date, end: date) -> dict[str, Any]:
    """Totals for one video over [start, end]."""
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            filters=f"video=={video_id}",
            startDate=start.isoformat(),
            endDate=end.isoformat(),
            metrics=VIDEO_METRICS,
        )
        .execute()
    )
    _, rows = _rows(response)
    return {
        "video_id": video_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "metrics": rows[0] if rows else {},
    }
