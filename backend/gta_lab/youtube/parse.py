"""Strict parsers: JSON body -> typed records. Raw bodies never leave this module.

Structural problems (not JSON, wrong types, missing or malformed IDs, non-numeric counts,
duplicate or unrequested items) raise ``MalformedResponseError`` and nothing from that
response is used. A single odd optional field (unexpected duration text, a thumbnail on a
non-YouTube host) is dropped to ``None`` and counted in ``field_anomalies`` instead.

Missing statistics stay ``None`` (shown as "Unavailable"), never 0. Nothing here infers a
Shorts flag: the API has no reliable public one and duration alone is not evidence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from ..db.sources import ChannelRecord, VideoRecord, VideoStatistics
from .errors import MalformedResponseError
from .ids import CHANNEL_ID_RE, PLAYLIST_ID_RE, VIDEO_ID_RE

_DURATION_RE = re.compile(r"^P(?:\d+W)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$")
_COUNT_RE = re.compile(r"^\d{1,19}$")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$")
_CATEGORY_RE = re.compile(r"^\d{1,4}$")
_THUMB_ORDER = ("high", "medium", "standard", "default", "maxres")
_MAX_TEXT = 1000


def _bad(what: str) -> MalformedResponseError:
    return MalformedResponseError(f"malformed response: {what}", reason="malformed")


def decode_json(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _bad("body is not JSON") from None
    if not isinstance(data, dict):
        raise _bad("top level is not an object")
    return data


def _items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("items", [])  # an empty result may omit "items"
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise _bad("items is not a list of objects")
    return items


def _obj(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key, {})
    if not isinstance(value, dict):
        raise _bad(f"{key} is not an object")
    return value


def next_page_token(data: dict[str, Any]) -> str | None:
    token = data.get("nextPageToken")
    if token is None:
        return None
    if not isinstance(token, str) or not token or len(token) > 512:
        raise _bad("nextPageToken")
    return token


@dataclass(frozen=True)
class VideoHints:
    """Status hints that are not stored as columns yet. Never a Shorts flag."""

    privacy_status: str | None = None
    upload_status: str | None = None
    default_audio_language: str | None = None
    missing_stats: tuple[str, ...] = ()


@dataclass
class VideosPage:
    records: list[VideoRecord] = field(default_factory=list)
    hints: dict[str, VideoHints] = field(default_factory=dict)
    field_anomalies: int = 0


class _Anomalies:
    def __init__(self) -> None:
        self.count = 0

    def text(self, obj: dict[str, Any], key: str) -> str | None:
        value = obj.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise _bad(f"{key} is not text")
        if len(value) > _MAX_TEXT:
            self.count += 1
            return None
        return value

    def matching(self, obj: dict[str, Any], key: str, pattern: re.Pattern[str]) -> str | None:
        value = self.text(obj, key)
        if value is not None and not pattern.match(value):
            self.count += 1
            return None
        return value


def _count(stats: dict[str, Any], key: str) -> int | None:
    value = stats.get(key)
    if value is None:
        return None  # hidden or not provided: stays NULL, rendered "Unavailable"
    if isinstance(value, bool):
        raise _bad(f"{key} is boolean")
    if isinstance(value, int):
        if value < 0:
            raise _bad(f"{key} is negative")
        return value
    if isinstance(value, str) and _COUNT_RE.match(value):
        return int(value)
    raise _bad(f"{key} is not a non-negative integer")


def _published(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _bad("publishedAt is not text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _bad("publishedAt is not a timestamp") from None
    if parsed.tzinfo is None:
        raise _bad("publishedAt has no timezone")
    return parsed.astimezone(UTC).replace(microsecond=0)


def _thumbnail(snippet: dict[str, Any], anomalies: _Anomalies) -> str | None:
    thumbs = _obj(snippet, "thumbnails")
    for size in _THUMB_ORDER:
        entry = thumbs.get(size)
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if not isinstance(url, str):
            continue
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme == "https" and (host == "ytimg.com" or host.endswith(".ytimg.com")):
            return url
        anomalies.count += 1  # never keep a thumbnail URL from an unexpected host
    return None


def parse_videos(body: bytes, requested_ids: Sequence[str]) -> VideosPage:
    data = decode_json(body)
    requested = set(requested_ids)
    page = VideosPage()
    anomalies = _Anomalies()
    for item in _items(data):
        vid = item.get("id")
        if not isinstance(vid, str) or not VIDEO_ID_RE.match(vid):
            raise _bad("video id")
        if vid not in requested:
            raise _bad("unrequested video returned")
        if vid in page.hints:
            raise _bad("duplicate video returned")
        snippet = _obj(item, "snippet")
        details = _obj(item, "contentDetails")
        status = _obj(item, "status")
        stats_obj = item.get("statistics")
        if stats_obj is not None and not isinstance(stats_obj, dict):
            raise _bad("statistics is not an object")

        channel_id = anomalies.matching(snippet, "channelId", CHANNEL_ID_RE)
        embeddable = status.get("embeddable")
        if embeddable is not None and not isinstance(embeddable, bool):
            raise _bad("embeddable is not boolean")

        statistics = None
        missing: tuple[str, ...] = ()
        if stats_obj is not None:
            statistics = VideoStatistics(
                view_count=_count(stats_obj, "viewCount"),
                like_count=_count(stats_obj, "likeCount"),
                comment_count=_count(stats_obj, "commentCount"),
            )
            missing = tuple(
                k for k in ("viewCount", "likeCount", "commentCount") if stats_obj.get(k) is None
            )

        page.records.append(
            VideoRecord(
                video_id=vid,
                channel_id=channel_id,
                channel_title=anomalies.text(snippet, "channelTitle"),
                title=anomalies.text(snippet, "title"),
                published_at=_published(snippet.get("publishedAt")),
                duration_iso=anomalies.matching(details, "duration", _DURATION_RE),
                category_id=anomalies.matching(snippet, "categoryId", _CATEGORY_RE),
                default_language=anomalies.matching(snippet, "defaultLanguage", _LANG_RE),
                thumbnail_url=_thumbnail(snippet, anomalies),
                embeddable=embeddable,
                statistics=statistics,
            )
        )
        page.hints[vid] = VideoHints(
            privacy_status=anomalies.text(status, "privacyStatus"),
            upload_status=anomalies.text(status, "uploadStatus"),
            default_audio_language=anomalies.matching(snippet, "defaultAudioLanguage", _LANG_RE),
            missing_stats=missing,
        )
    page.field_anomalies = anomalies.count
    return page


def parse_channels(body: bytes, requested_ids: Sequence[str] | None) -> list[ChannelRecord]:
    """``requested_ids=None`` for a ``forHandle`` lookup (at most one channel back)."""
    data = decode_json(body)
    items = _items(data)
    if requested_ids is None and len(items) > 1:
        raise _bad("handle lookup returned more than one channel")
    allowed = None if requested_ids is None else set(requested_ids)
    seen: set[str] = set()
    out: list[ChannelRecord] = []
    anomalies = _Anomalies()
    for item in items:
        cid = item.get("id")
        if not isinstance(cid, str) or not CHANNEL_ID_RE.match(cid):
            raise _bad("channel id")
        if (allowed is not None and cid not in allowed) or cid in seen:
            raise _bad("unrequested or duplicate channel returned")
        seen.add(cid)
        related = _obj(_obj(item, "contentDetails"), "relatedPlaylists")
        uploads = related.get("uploads")
        valid_uploads = isinstance(uploads, str) and PLAYLIST_ID_RE.match(uploads)
        if uploads is not None and not valid_uploads:
            raise _bad("uploads playlist id")
        out.append(
            ChannelRecord(
                channel_id=cid,
                title=anomalies.text(_obj(item, "snippet"), "title"),
                uploads_playlist_id=uploads,
            )
        )
    return out


def parse_search_ids(body: bytes) -> tuple[list[str], str | None]:
    data = decode_json(body)
    ids: list[str] = []
    for item in _items(data):
        ident = _obj(item, "id")
        vid = ident.get("videoId")
        if not isinstance(vid, str) or not VIDEO_ID_RE.match(vid):
            raise _bad("search result video id")
        ids.append(vid)
    return ids, next_page_token(data)


def parse_playlist_ids(body: bytes) -> tuple[list[str], str | None]:
    data = decode_json(body)
    ids: list[str] = []
    for item in _items(data):
        vid = _obj(item, "contentDetails").get("videoId")
        if not isinstance(vid, str) or not VIDEO_ID_RE.match(vid):
            raise _bad("playlist item video id")
        ids.append(vid)
    return ids, next_page_token(data)


def parse_error(body: bytes) -> tuple[str | None, str | None]:
    """Return (first error reason, google.rpc ErrorInfo reason) from an error body.

    The human ``message`` is read only to recognise the invalid-key case; it is never
    returned or stored.
    """
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, None
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return None, None
    reason = None
    errors = err.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        r = errors[0].get("reason")
        reason = r if isinstance(r, str) and len(r) <= 64 else None
    info_reason = None
    details = err.get("details")
    if isinstance(details, list):
        for d in details:
            if isinstance(d, dict) and isinstance(d.get("reason"), str):
                info_reason = d["reason"][:64]
                break
    message = err.get("message")
    if info_reason is None and isinstance(message, str) and "API key not valid" in message:
        info_reason = "API_KEY_INVALID"
    return reason, info_reason
