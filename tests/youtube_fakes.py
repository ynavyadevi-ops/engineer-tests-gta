"""In-memory fakes for the YouTube adapter tests.

Every ID and number here is a synthetic placeholder shaped like the API's (so the
parsers accept it). None is a real video, channel or metric, nothing is stored, and the
fake transport never touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from gta_lab.youtube.client import RetryPolicy, YouTubeClient
from gta_lab.youtube.quota import QuotaLedger
from gta_lab.youtube.transport import HttpResponse, TransportFailure

SENTINEL_KEY = "AIzaSENTINEL-not-a-real-key-000000000000"  # synthetic, key-shaped


def vid(n: int) -> str:
    """Synthetic 11-char video ID (``zzT`` prefix + digits)."""
    return f"zzT{n:08d}"


def cid(n: int) -> str:
    return f"UCzzTEST{n:016d}"


def upl(n: int) -> str:
    return f"UUzzTEST{n:016d}"


def video_item(video_id: str, **over: object) -> dict:
    item = {
        "id": video_id,
        "snippet": {
            "publishedAt": "2025-01-02T03:04:05Z",
            "channelId": cid(1),
            "channelTitle": "Synthetic channel",
            "title": f"Synthetic title {video_id}",
            "categoryId": "20",
            "defaultAudioLanguage": "en",
            "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}},
        },
        "contentDetails": {"duration": "PT10M2S"},
        "statistics": {"viewCount": "1000", "likeCount": "10", "commentCount": "1"},
        "status": {"embeddable": True, "privacyStatus": "public", "uploadStatus": "processed"},
    }
    item.update(over)
    return item


def ok(payload: dict) -> HttpResponse:
    return HttpResponse(200, json.dumps(payload).encode())


def api_error(
    status: int,
    reason: str | None = None,
    *,
    info: str | None = None,
    message: str = "synthetic error",
    headers: dict | None = None,
) -> HttpResponse:
    err: dict = {"code": status, "message": message}
    if reason:
        err["errors"] = [{"reason": reason, "domain": "youtube.quota", "message": message}]
    if info:
        err["details"] = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": info}]
    return HttpResponse(status, json.dumps({"error": err}).encode(), headers or {})


Responder = Callable[[str, dict[str, list[str]]], HttpResponse]


class FakeTransport:
    """Replays queued responses (or a responder) and records each request URL."""

    def __init__(self, *responses: HttpResponse | Exception, responder: Responder | None = None):
        self.queue = list(responses)
        self.responder = responder
        self.urls: list[str] = []
        self.timeouts: list[float] = []

    def send(self, url: str, timeout: float) -> HttpResponse:
        self.urls.append(url)
        self.timeouts.append(timeout)
        if self.responder is not None:
            parts = urlsplit(url)
            return self.responder(parts.path.rsplit("/", 1)[-1], parse_qs(parts.query))
        if not self.queue:
            raise AssertionError("unexpected extra request")
        nxt = self.queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def params(self, i: int = -1) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.urls[i]).query)


def make_client(
    transport: FakeTransport, *, search: int = 100, units: int = 10_000, attempts: int = 4
) -> tuple[YouTubeClient, list[float]]:
    sleeps: list[float] = []
    client = YouTubeClient(
        SENTINEL_KEY,
        QuotaLedger(search, units),
        transport=transport,
        retry=RetryPolicy(max_attempts=attempts),
        sleep=sleeps.append,
    )
    return client, sleeps


__all__ = [
    "SENTINEL_KEY",
    "FakeTransport",
    "TransportFailure",
    "api_error",
    "cid",
    "make_client",
    "ok",
    "upl",
    "vid",
    "video_item",
]
