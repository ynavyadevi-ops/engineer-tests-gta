"""Read-only YouTube Data API v3 client: search.list, videos.list, channels.list,
playlistItems.list. Nothing else is callable.

* Partial responses: every call sends a fixed ``part`` and ``fields`` mask. No
  descriptions, comments, captions or files are ever requested.
* Quota: each attempt is charged to a ``QuotaLedger`` *before* it is sent, so a local
  budget stops the run cleanly with nothing in flight.
* Retries: only timeouts, network failures, HTTP 429/5xx and 403 rate-limit reasons, with
  full-jitter exponential backoff and a hard attempt cap. Bad key, permission, quota
  exhaustion, bad requests and malformed bodies are never retried.
* Resume: paged and batched helpers return what they finished plus a resume point
  (page token or remaining IDs) and the stop kind, instead of losing partial work.
* Secrets: the key lives in a private holder, is added to the URL only at send time, and
  never appears in logs, exceptions, ``repr`` or results. Log lines carry method, status,
  attempt and units only.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode

from ..db.sources import ChannelRecord
from . import parse
from .errors import (
    BadKeyError,
    BadRequestError,
    MalformedResponseError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExhaustedError,
    StopError,
    TransientError,
    YouTubeError,
)
from .ids import CHANNEL_ID_RE, HANDLE_RE, PLAYLIST_ID_RE, VIDEO_ID_RE
from .quota import MAX_IDS_PER_REQUEST, MAX_RESULTS_PER_PAGE, Method, QuotaLedger
from .transport import API_BASE, HttpResponse, Transport, TransportFailure, UrllibTransport

log = logging.getLogger("gta_lab.youtube")

# Partial-response masks. Kept deliberately minimal; see docs/YOUTUBE_POLICY.md.
VIDEO_PARTS = "snippet,contentDetails,statistics,status"
VIDEO_FIELDS = (
    "items(id,"
    "snippet(publishedAt,channelId,channelTitle,title,categoryId,defaultLanguage,"
    "defaultAudioLanguage,thumbnails),"
    "contentDetails(duration),"
    "statistics(viewCount,likeCount,commentCount),"
    "status(embeddable,privacyStatus,uploadStatus))"
)
CHANNEL_PARTS = "snippet,contentDetails"
CHANNEL_FIELDS = "items(id,snippet(title),contentDetails(relatedPlaylists(uploads)))"
SEARCH_FIELDS = "nextPageToken,items(id(videoId))"
PLAYLIST_FIELDS = "nextPageToken,items(contentDetails(videoId))"

SearchOrder = Literal["relevance", "date", "viewCount", "rating"]
_SEARCH_ORDERS = {"relevance", "date", "viewCount", "rating"}
_RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "RATE_LIMIT_EXCEEDED"}
_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "RESOURCE_EXHAUSTED"}
_BAD_KEY_REASONS = {"keyInvalid", "keyExpired", "API_KEY_INVALID", "API_KEY_EXPIRED"}
_RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_QUERY_LEN = 200
MAX_PAGES_HARD_CAP = 20


class _Secret:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "_Secret([REDACTED])"

    __str__ = __repr__


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4  # 1 try + up to 3 retries
    base_delay: float = 0.5
    max_delay: float = 8.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 6:
            raise ValueError("max_attempts must be 1..6")


@dataclass
class PagedIds:
    """Result of a paged discovery call. ``resume_token`` is set when it stopped early."""

    video_ids: list[str] = field(default_factory=list)
    pages: int = 0
    complete: bool = False
    resume_token: str | None = None
    stop_kind: str | None = None


@dataclass
class Hydration:
    """Result of hydrating IDs with videos.list, batch by batch."""

    batches: list[tuple[list[str], parse.VideosPage]] = field(default_factory=list)
    remaining_ids: list[str] = field(default_factory=list)
    stop_kind: str | None = None

    @property
    def records(self) -> list:
        return [r for _, page in self.batches for r in page.records]

    @property
    def not_returned(self) -> list[str]:
        out: list[str] = []
        for requested, page in self.batches:
            got = {r.video_id for r in page.records}
            out.extend(v for v in requested if v not in got)
        return out


class YouTubeClient:
    def __init__(
        self,
        api_key: str,
        ledger: QuotaLedger,
        *,
        transport: Transport | None = None,
        timeout: float = 15.0,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise BadKeyError("YouTube API key is not configured", reason="missing_key")
        if not 1.0 <= timeout <= 60.0:
            raise ValueError("timeout must be 1..60 seconds")
        self._key = _Secret(api_key.strip())
        self.ledger = ledger
        self._transport = transport or UrllibTransport()
        self.timeout = timeout
        self.retry = retry or RetryPolicy()
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not crypto
        self.retries = 0

    def __repr__(self) -> str:
        return f"YouTubeClient(timeout={self.timeout}, ledger={self.ledger.snapshot()})"

    # ---------------- core request loop ----------------
    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        cap = min(self.retry.max_delay, self.retry.base_delay * (2 ** (attempt - 1)))
        delay = self._rng.uniform(0, cap)  # full jitter
        if retry_after and retry_after.isdigit():
            delay = max(delay, min(float(retry_after), self.retry.max_delay))
        return delay

    def _get(self, method: Method, resource: str, params: dict[str, str]) -> bytes:
        query = urlencode(sorted(params.items()))
        last: YouTubeError | None = None
        for attempt in range(1, self.retry.max_attempts + 1):
            self.ledger.charge(method)  # raises BudgetExhaustedError before sending
            url = f"{API_BASE}{resource}?{query}&{urlencode({'key': self._key.get()})}"
            try:
                resp = self._transport.send(url, self.timeout)
            except TransportFailure as exc:
                last = TransientError(f"{method}: {exc.kind}", reason=exc.kind)
                log.info("youtube %s attempt=%d outcome=%s", method, attempt, exc.kind)
            else:
                log.info("youtube %s attempt=%d status=%d", method, attempt, resp.status)
                if resp.status == 200:
                    return resp.body
                last = self._classify(method, resp)
                if not last.retryable:
                    raise last
            finally:
                url = ""  # do not leave the keyed URL in a frame local
            if attempt < self.retry.max_attempts:
                self.retries += 1
                self._sleep(self._backoff(attempt, getattr(last, "retry_after", None)))
        if last is None:  # pragma: no cover - max_attempts >= 1
            raise TransientError(f"{method}: no attempt made")
        raise last

    @staticmethod
    def _classify(method: Method, resp: HttpResponse) -> YouTubeError:
        reason, info = parse.parse_error(resp.body)
        status = resp.status
        reasons = {r for r in (reason, info) if r}
        label = reason or info or "unknown"
        if status in _RETRY_STATUSES or (status == 403 and reasons & _RATE_LIMIT_REASONS):
            err = TransientError(f"{method}: HTTP {status} ({label})", status=status, reason=label)
            err.retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            return err
        if status == 401 or reasons & _BAD_KEY_REASONS:
            return BadKeyError(f"{method}: API key rejected", status=status, reason=label)
        if status == 403 and reasons & _QUOTA_REASONS:
            return QuotaExhaustedError(
                f"{method}: YouTube quota exhausted; resume after the daily reset",
                status=status,
                reason=label,
            )
        if status == 403:
            return PermissionDeniedError(
                f"{method}: access denied ({label})", status=status, reason=label
            )
        if status == 404:
            return NotFoundError(f"{method}: not found ({label})", status=status, reason=label)
        if status == 400:
            return BadRequestError(f"{method}: bad request ({label})", status=status, reason=label)
        return MalformedResponseError(f"{method}: unexpected HTTP {status}", status=status)

    # ---------------- videos.list ----------------
    def videos(self, video_ids: Sequence[str]) -> parse.VideosPage:
        """One videos.list call for at most 50 unique, valid IDs."""
        ids = list(video_ids)
        if not 1 <= len(ids) <= MAX_IDS_PER_REQUEST or len(set(ids)) != len(ids):
            raise ValueError("videos.list takes 1..50 unique IDs")
        if not all(isinstance(v, str) and VIDEO_ID_RE.match(v) for v in ids):
            raise ValueError("invalid video ID in batch")
        body = self._get(
            "videos.list",
            "videos",
            {
                "part": VIDEO_PARTS,
                "id": ",".join(ids),
                "fields": VIDEO_FIELDS,
            },
        )
        return parse.parse_videos(body, ids)

    def hydrate(self, video_ids: Sequence[str]) -> Hydration:
        """Hydrate IDs in batches of 50 (deduplicated, order kept). Stops cleanly on a stop
        error or exhausted retries and reports the IDs not yet attempted."""
        unique = list(dict.fromkeys(video_ids))
        result = Hydration()
        for start in range(0, len(unique), MAX_IDS_PER_REQUEST):
            batch = unique[start : start + MAX_IDS_PER_REQUEST]
            try:
                page = self.videos(batch)
            except (StopError, TransientError, MalformedResponseError) as exc:
                result.remaining_ids = unique[start:]
                result.stop_kind = _stop_kind(exc)
                return result
            result.batches.append((batch, page))
        return result

    # ---------------- channels.list ----------------
    def channels(self, channel_ids: Sequence[str]) -> list[ChannelRecord]:
        ids = list(channel_ids)
        if not 1 <= len(ids) <= MAX_IDS_PER_REQUEST or len(set(ids)) != len(ids):
            raise ValueError("channels.list takes 1..50 unique IDs")
        if not all(isinstance(c, str) and CHANNEL_ID_RE.match(c) for c in ids):
            raise ValueError("invalid channel ID in batch")
        body = self._get(
            "channels.list",
            "channels",
            {
                "part": CHANNEL_PARTS,
                "id": ",".join(ids),
                "fields": CHANNEL_FIELDS,
            },
        )
        return parse.parse_channels(body, ids)

    def channel_for_handle(self, handle: str) -> ChannelRecord | None:
        if not isinstance(handle, str) or not HANDLE_RE.match(handle):
            raise ValueError("invalid handle")
        body = self._get(
            "channels.list",
            "channels",
            {"part": CHANNEL_PARTS, "forHandle": "@" + handle, "fields": CHANNEL_FIELDS},
        )
        found = parse.parse_channels(body, None)
        return found[0] if found else None

    # ---------------- playlistItems.list ----------------
    def playlist_video_ids(
        self,
        playlist_id: str,
        *,
        max_pages: int = 1,
        per_page: int = MAX_RESULTS_PER_PAGE,
        page_token: str | None = None,
    ) -> PagedIds:
        if not isinstance(playlist_id, str) or not PLAYLIST_ID_RE.match(playlist_id):
            raise ValueError("invalid playlist ID")
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "fields": PLAYLIST_FIELDS,
        }
        return self._paged(
            "playlistItems.list",
            "playlistItems",
            params,
            max_pages,
            per_page,
            page_token,
            parse.parse_playlist_ids,
        )

    def uploads_video_ids(
        self, channel_ids: Sequence[str], *, max_pages_per_channel: int = 1
    ) -> tuple[dict[str, PagedIds], str | None]:
        """Discovery through each channel's official uploads playlist (1 unit/page) rather
        than search (separate 100-call bucket). Returns per-channel results and a stop kind
        if a channels.list lookup failed."""
        out: dict[str, PagedIds] = {}
        ids = list(dict.fromkeys(channel_ids))
        for start in range(0, len(ids), MAX_IDS_PER_REQUEST):
            batch = ids[start : start + MAX_IDS_PER_REQUEST]
            try:
                channels = self.channels(batch)
            except (StopError, TransientError, MalformedResponseError) as exc:
                return out, _stop_kind(exc)
            for ch in channels:
                if ch.uploads_playlist_id is None:
                    continue
                res = self.playlist_video_ids(
                    ch.uploads_playlist_id, max_pages=max_pages_per_channel
                )
                out[ch.channel_id] = res
                if res.stop_kind in (
                    "bad_key",
                    "permission",
                    "quota_exhausted",
                    "budget_exhausted",
                ):
                    return out, res.stop_kind
        return out, None

    # ---------------- search.list ----------------
    def search_video_ids(
        self,
        query: str,
        *,
        order: SearchOrder = "relevance",
        max_pages: int = 1,
        per_page: int = MAX_RESULTS_PER_PAGE,
        page_token: str | None = None,
        published_after: str | None = None,
        region_code: str | None = None,
        relevance_language: str | None = None,
        video_category_id: str | None = None,
    ) -> PagedIds:
        """search.list for videos only, IDs only (hydrate with videos.list afterwards)."""
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LEN:
            raise ValueError(f"query must be 1..{MAX_QUERY_LEN} characters")
        if order not in _SEARCH_ORDERS:
            raise ValueError("unsupported order")
        params = {
            "part": "id",
            "type": "video",
            "q": query.strip(),
            "order": order,
            "fields": SEARCH_FIELDS,
        }
        optional = {
            "publishedAfter": published_after,
            "regionCode": region_code,
            "relevanceLanguage": relevance_language,
            "videoCategoryId": video_category_id,
        }
        for key, value in optional.items():
            if value is not None:
                if not isinstance(value, str) or not value or len(value) > 40:
                    raise ValueError(f"invalid {key}")
                params[key] = value
        return self._paged(
            "search.list", "search", params, max_pages, per_page, page_token, parse.parse_search_ids
        )

    # ---------------- shared pagination ----------------
    def _paged(
        self,
        method: Method,
        resource: str,
        params: dict[str, str],
        max_pages: int,
        per_page: int,
        page_token: str | None,
        parser: Callable[[bytes], tuple[list[str], str | None]],
    ) -> PagedIds:
        if not 1 <= max_pages <= MAX_PAGES_HARD_CAP:
            raise ValueError(f"max_pages must be 1..{MAX_PAGES_HARD_CAP}")
        if not 1 <= per_page <= MAX_RESULTS_PER_PAGE:
            raise ValueError(f"per_page must be 1..{MAX_RESULTS_PER_PAGE}")
        result = PagedIds()
        token = page_token
        seen: set[str] = set()
        for _ in range(max_pages):
            page_params = dict(params, maxResults=str(per_page))
            if token:
                page_params["pageToken"] = token
            try:
                ids, next_token = parser(self._get(method, resource, page_params))
            except (StopError, TransientError, MalformedResponseError) as exc:
                result.resume_token = token
                result.stop_kind = _stop_kind(exc)
                return result
            result.pages += 1
            for vid in ids:
                if vid not in seen:
                    seen.add(vid)
                    result.video_ids.append(vid)
            if not next_token:
                result.complete = True
                return result
            if next_token == token:
                result.stop_kind = "malformed"  # a repeating token would loop forever
                result.resume_token = token
                return result
            token = next_token
        result.resume_token = token  # page cap reached: resume from here next time
        return result


def _stop_kind(exc: YouTubeError) -> str:
    if isinstance(exc, StopError):
        return exc.kind
    if isinstance(exc, TransientError):
        return "transient"
    return "malformed"
