"""Analytics tools against a fake Analytics API client."""

from datetime import date

import pytest
from fakes import http_error, report
from fastmcp.exceptions import ToolError

from vunm_youtube_mcp import analytics

COLUMNS = ["day", "views", "likes"]


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr(analytics, "reporting_today", lambda: date(2026, 9, 30))


def test_reporting_time_zone_is_pacific():
    assert analytics.REPORTING_TZ.key == "America/Los_Angeles"


def test_default_window_is_28_days_ending_2_days_ago():
    assert analytics.resolve_window(None, None, today=date(2026, 9, 30)) == (
        date(2026, 9, 1),
        date(2026, 9, 28),
    )


def test_window_rejects_start_after_end():
    with pytest.raises(ToolError, match="is after end_date"):
        analytics.resolve_window(date(2026, 9, 2), date(2026, 9, 1))


async def test_channel_report_defaults_to_daily_rows(provider, call_tool, today):
    provider.analytics_client.respond(
        "reports.query", report(COLUMNS, [["2026-09-01", 5, 1], ["2026-09-02", 7, 0]])
    )

    result = await call_tool("youtube_analytics_report")

    assert result.structured_content == {
        "start_date": "2026-09-01",
        "end_date": "2026-09-28",
        "dimension": "day",
        "columns": COLUMNS,
        "rows": [
            {"day": "2026-09-01", "views": 5, "likes": 1},
            {"day": "2026-09-02", "views": 7, "likes": 0},
        ],
    }
    assert provider.analytics_client.calls_to("reports.query") == [
        {
            "ids": "channel==MINE",
            "startDate": "2026-09-01",
            "endDate": "2026-09-28",
            "metrics": analytics.CHANNEL_METRICS,
            "dimensions": "day",
            "sort": "day",
        }
    ]


async def test_channel_report_totals_without_a_dimension(provider, call_tool):
    provider.analytics_client.respond("reports.query", report(["views"], [[42]]))

    result = await call_tool(
        "youtube_analytics_report",
        {"start_date": "2026-08-01", "end_date": "2026-08-31", "dimensions": None},
    )

    assert result.structured_content["rows"] == [{"views": 42}]
    query = provider.analytics_client.calls_to("reports.query")[0]
    assert "dimensions" not in query
    assert "sort" not in query


async def test_month_report_moves_dates_to_the_first_of_the_month(provider, call_tool):
    provider.analytics_client.respond("reports.query", report(["month", "views"], []))

    result = await call_tool(
        "youtube_analytics_report",
        {"start_date": "2026-06-15", "end_date": "2026-09-10", "dimensions": "month"},
    )

    assert (result.structured_content["start_date"], result.structured_content["end_date"]) == (
        "2026-06-01",
        "2026-09-01",
    )
    query = provider.analytics_client.calls_to("reports.query")[0]
    assert (query["startDate"], query["endDate"], query["sort"]) == (
        "2026-06-01",
        "2026-09-01",
        "month",
    )


async def test_country_report_sorts_by_views(provider, call_tool, today):
    provider.analytics_client.respond("reports.query", report(["country", "views"], [["VN", 9]]))

    await call_tool("youtube_analytics_report", {"dimensions": "country"})

    assert provider.analytics_client.calls_to("reports.query")[0]["sort"] == "-views"


@pytest.mark.parametrize(
    "arguments",
    [
        {"start_date": "2026-13-01"},
        {"end_date": "01/09/2026"},
        {"dimensions": "week"},
    ],
)
async def test_channel_report_rejects_invalid_arguments(provider, call_tool, arguments):
    result = await call_tool("youtube_analytics_report", arguments)

    assert result.is_error
    assert provider.analytics_client.calls == []


async def test_channel_report_rejects_start_after_end(provider, call_tool):
    result = await call_tool(
        "youtube_analytics_report", {"start_date": "2026-09-10", "end_date": "2026-09-01"}
    )

    assert result.is_error
    assert "is after end_date" in result.content[0].text
    assert provider.analytics_client.calls == []


async def test_video_analytics_filters_by_video(provider, call_tool, today):
    provider.analytics_client.respond("reports.query", report(["views", "likes"], [[120, 8]]))

    result = await call_tool("youtube_video_analytics", {"video_id": "vid00000001"})

    assert result.structured_content == {
        "video_id": "vid00000001",
        "start_date": "2026-09-01",
        "end_date": "2026-09-28",
        "metrics": {"views": 120, "likes": 8},
    }
    query = provider.analytics_client.calls_to("reports.query")[0]
    assert query["filters"] == "video==vid00000001"
    assert query["metrics"] == analytics.VIDEO_METRICS


async def test_video_analytics_without_rows(provider, call_tool, today):
    provider.analytics_client.respond("reports.query", report(["views"], []))

    result = await call_tool("youtube_video_analytics", {"video_id": "vid00000001"})

    assert result.structured_content["metrics"] == {}


async def test_quota_error_is_explained(provider, call_tool, today):
    provider.analytics_client.respond("reports.query", http_error(403, "quotaExceeded"))

    result = await call_tool("youtube_analytics_report")

    assert result.is_error
    assert "resets at midnight Pacific Time" in result.content[0].text
