"""Turn Google API failures into `ToolError`s that say what to do next.

An MCP client shows a `ToolError` message to the model as-is, so each message
names the cause and, where there is one, the fix.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import httplib2
from fastmcp.exceptions import ToolError
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

from vunm_youtube_mcp.auth import AuthRequired, auth_command
from vunm_youtube_mcp.config import Mode

QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}
RATE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "RATE_LIMIT_EXCEEDED"}
SCOPE_REASONS = {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}
NOT_FOUND_REASONS = {"notFound", "videoNotFound", "channelNotFound", "playlistNotFound"}


def http_error_reasons(exc: HttpError) -> list[str]:
    """Every machine-readable reason in the error body (legacy `errors` and `details`)."""
    try:
        error = json.loads(exc.content.decode("utf-8"))["error"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return []
    reasons = [
        item["reason"]
        for key in ("errors", "details")
        for item in error.get(key) or []
        if isinstance(item, dict) and item.get("reason")
    ]
    if error.get("status"):
        reasons.append(error["status"])
    return reasons


def tool_error_from_http(exc: HttpError, mode: Mode) -> ToolError:
    """Map an `HttpError` to a `ToolError` by status and reason."""
    status = exc.status_code or exc.resp.status
    reasons = http_error_reasons(exc)
    reason_set = set(reasons)
    message = exc.reason or "no message"
    first_reason = reasons[0] if reasons else "unknown"

    if reason_set & QUOTA_REASONS:
        return ToolError(
            "The YouTube API quota of this Google Cloud project is used up for today; "
            "it resets at midnight Pacific Time. Most calls share 10,000 units a day, "
            f"while search has its own bucket of 100 calls a day. ({message})"
        )
    if status == 429 or reason_set & RATE_REASONS:
        return ToolError(
            f"Google is rate-limiting these requests; wait a moment and retry. ({message})"
        )
    if "commentsDisabled" in reason_set:
        return ToolError(f"Comments are disabled for this video. ({message})")
    if status == 401:
        return AuthRequired(f"Google rejected the saved token ({message})", mode)
    if reason_set & SCOPE_REASONS:
        return ToolError(
            f"The saved token lacks a permission this call needs ({message}). "
            f"Run `{auth_command(mode)}` to authorize again."
        )
    if status == 403:
        return ToolError(
            f"YouTube denied access ({first_reason}): {message}. The authorized account "
            "may not own this resource."
        )
    if status == 404 or reason_set & NOT_FOUND_REASONS:
        return ToolError(f"Not found ({first_reason}): {message}")
    return ToolError(f"YouTube API error {status} ({first_reason}): {message}")


@contextmanager
def google_api_errors(mode: Mode) -> Iterator[None]:
    """Re-raise Google client failures as `ToolError`s; let `ToolError`s through."""
    try:
        yield
    except ToolError:
        raise
    except HttpError as exc:
        raise tool_error_from_http(exc, mode) from exc
    except RefreshError as exc:
        detail = exc.args[0] if exc.args else exc
        raise AuthRequired(f"Google refused to refresh the saved token ({detail})", mode) from exc
    except (TransportError, httplib2.HttpLib2Error, TimeoutError, ConnectionError) as exc:
        raise ToolError(f"Could not reach Google's API: {exc}") from exc
