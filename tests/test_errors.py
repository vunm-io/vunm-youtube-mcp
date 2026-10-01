"""Every mapping from a Google client failure to a ToolError."""

import httplib2
import pytest
from fakes import http_error
from fastmcp.exceptions import ToolError
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

from vunm_youtube_mcp.auth import AuthRequired
from vunm_youtube_mcp.config import Mode
from vunm_youtube_mcp.errors import google_api_errors, http_error_reasons, tool_error_from_http


def _raised(exc: BaseException, mode: Mode = Mode.FULL) -> ToolError:
    with pytest.raises(ToolError) as raised, google_api_errors(mode):
        raise exc
    return raised.value


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        (403, "quotaExceeded", "resets at midnight Pacific Time"),
        (403, "dailyLimitExceeded", "search has its own bucket of 100 calls a day"),
        (403, "rateLimitExceeded", "rate-limiting"),
        (429, "tooManyRequests", "rate-limiting"),
        (403, "commentsDisabled", "Comments are disabled"),
        (403, "insufficientPermissions", "lacks a permission"),
        (403, "forbidden", "YouTube denied access (forbidden)"),
        (404, "videoNotFound", "Not found (videoNotFound)"),
        (404, "notFound", "Not found (notFound)"),
        (400, "badRequest", "YouTube API error 400 (badRequest): synthetic error"),
        (500, "backendError", "YouTube API error 500 (backendError)"),
    ],
)
def test_http_errors_map_by_reason(status, reason, expected):
    error = _raised(http_error(status, reason))

    assert expected in str(error)


def test_unauthorized_means_authorize_again():
    error = _raised(http_error(401, "authError"))

    assert isinstance(error, AuthRequired)
    assert "Google rejected the saved token" in str(error)


def test_scope_errors_name_the_auth_command_for_the_mode():
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
        }
    ]
    error = _raised(http_error(403, "forbidden", details=details), Mode.READ_ONLY)

    assert "lacks a permission" in str(error)
    assert "`vunm-youtube-mcp auth --mode read-only`" in str(error)


def test_reasons_come_from_errors_details_and_status():
    exc = http_error(403, "forbidden", status="PERMISSION_DENIED", details=[{"reason": "X"}])

    assert http_error_reasons(exc) == ["forbidden", "X", "PERMISSION_DENIED"]


def test_a_body_that_is_not_json_still_maps():
    exc = HttpError(httplib2.Response({"status": 502}), b"<html>Bad Gateway</html>")

    error = tool_error_from_http(exc, Mode.FULL)

    assert str(error).startswith("YouTube API error 502 (unknown)")


def test_refresh_error_during_a_call_means_authorize_again():
    error = _raised(RefreshError("invalid_grant: Token has been expired or revoked."))

    assert isinstance(error, AuthRequired)
    assert "invalid_grant" in str(error)


@pytest.mark.parametrize(
    "exc",
    [TransportError("connection reset"), httplib2.ServerNotFoundError("no DNS"), TimeoutError()],
)
def test_network_failures(exc):
    assert "Could not reach Google's API" in str(_raised(exc))


def test_tool_errors_pass_through_unchanged():
    original = ToolError("already explained")

    assert _raised(original) is original
