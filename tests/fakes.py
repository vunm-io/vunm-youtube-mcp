"""Hand-written fakes for googleapiclient clients, and synthetic API payloads.

`FakeResource` answers ``client.<collection>().<method>(**kwargs).execute()``
from a script and records every call, so tests can assert both the result and
the exact request. All IDs and names here are synthetic.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any

import httplib2
from googleapiclient.errors import HttpError

CHANNEL_ID = "UCexampleChannel00000000"
UPLOADS_ID = "UUexampleChannel00000000"


class FakeResource:
    """A scripted API client: `respond(method, *responses)`, then read `calls`.

    Each call to `method` (for example ``"videos.list"``) pops the next queued
    response; an exception instance is raised instead of returned. A call with
    nothing queued fails the test.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._queued: dict[str, deque[Any]] = defaultdict(deque)

    def respond(self, method: str, *responses: Any) -> FakeResource:
        self._queued[method].extend(responses)
        return self

    def calls_to(self, method: str) -> list[dict[str, Any]]:
        return [kwargs for name, kwargs in self.calls if name == method]

    def __getattr__(self, collection: str):
        if collection.startswith("_"):
            raise AttributeError(collection)
        return lambda: _Collection(self, collection)

    def _execute(self, method: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((method, kwargs))
        queue = self._queued.get(method)
        if not queue:
            raise AssertionError(f"unexpected call: {method}({kwargs})")
        response = queue.popleft()
        if isinstance(response, BaseException):
            raise response
        return response


class _Collection:
    def __init__(self, root: FakeResource, name: str) -> None:
        self._root = root
        self._name = name

    def __getattr__(self, method: str):
        if method.startswith("_"):
            raise AttributeError(method)

        def call(**kwargs: Any) -> _Request:
            return _Request(self._root, f"{self._name}.{method}", kwargs)

        return call


class _Request:
    def __init__(self, root: FakeResource, method: str, kwargs: dict[str, Any]) -> None:
        self._root = root
        self._method = method
        self._kwargs = kwargs

    def execute(self, **_: Any) -> Any:
        return self._root._execute(self._method, self._kwargs)


class FakeProvider:
    """A `ServiceProvider` that hands out two `FakeResource`s."""

    def __init__(self) -> None:
        self.data_client = FakeResource()
        self.analytics_client = FakeResource()

    def data(self) -> FakeResource:
        return self.data_client

    def analytics(self) -> FakeResource:
        return self.analytics_client


def http_error(code: int, reason: str, message: str = "synthetic error", **extra) -> HttpError:
    """An `HttpError` with the JSON body shape Google APIs return; `extra` adds fields."""
    error = {
        "code": code,
        "message": message,
        "errors": [{"message": message, "domain": "youtube.synthetic", "reason": reason}],
        **extra,
    }
    return HttpError(httplib2.Response({"status": code}), json.dumps({"error": error}).encode())


def channel_response(**statistics: str) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": CHANNEL_ID,
                "snippet": {
                    "title": "Example Channel",
                    "description": "A synthetic channel.",
                    "customUrl": "@example",
                    "publishedAt": "2020-01-01T00:00:00Z",
                },
                "statistics": {
                    "subscriberCount": "1200",
                    "viewCount": "34000",
                    "videoCount": "56",
                    "hiddenSubscriberCount": False,
                    **statistics,
                },
                "contentDetails": {"relatedPlaylists": {"uploads": UPLOADS_ID}},
            }
        ]
    }


def playlist_page(video_ids: list[str], next_page_token: str | None = None) -> dict[str, Any]:
    page: dict[str, Any] = {
        "items": [
            {
                "snippet": {"title": f"Video {video_id}", "publishedAt": "2026-09-01T00:00:00Z"},
                "status": {"privacyStatus": "public"},
                "contentDetails": {"videoId": video_id},
            }
            for video_id in video_ids
        ]
    }
    if next_page_token:
        page["nextPageToken"] = next_page_token
    return page


def video_item(video_id: str, **snippet: Any) -> dict[str, Any]:
    return {
        "id": video_id,
        "snippet": {
            "title": f"Video {video_id}",
            "description": "A synthetic description.",
            "tags": ["example", "synthetic"],
            "categoryId": "27",
            "publishedAt": "2026-09-01T00:00:00Z",
            **snippet,
        },
        "status": {"privacyStatus": "private"},
        "statistics": {"viewCount": "10", "likeCount": "2", "commentCount": "1"},
        "contentDetails": {"duration": "PT4M13S"},
    }


def comment_thread(comment_id: str, text: str) -> dict[str, Any]:
    return {
        "id": comment_id,
        "snippet": {
            "totalReplyCount": 1,
            "topLevelComment": {
                "snippet": {
                    "authorDisplayName": "Example Viewer",
                    "textDisplay": text,
                    "likeCount": 3,
                    "publishedAt": "2026-09-02T00:00:00Z",
                }
            },
        },
    }


def report(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"columnHeaders": [{"name": name} for name in columns], "rows": rows}
