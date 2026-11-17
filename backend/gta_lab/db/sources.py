"""Source repository: videos, channels and current public statistics.

Input is already-parsed, typed records (``VideoRecord``); raw API response bodies are
never accepted or stored. All reads take ``now`` from the database clock and never return
a row whose ``expires_at_utc`` has passed, whatever the last refresh outcome was.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from ..clock import from_db_ts, to_db_ts
from .connection import Database
from .retention import RetentionPolicy, purge_videos

MAX_IDS_PER_BATCH = 50  # videos.list / channels.list accept at most 50 IDs per call
MAX_LIST_LIMIT = 200  # bounded reads: never pull the whole corpus into memory or context

VideoEndpoint = Literal["videos.list", "search.list", "playlistItems.list", "fixture"]
ChannelEndpoint = Literal["channels.list", "search.list", "fixture"]
_LIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

VideoState = Literal["available", "inaccessible", "expired", "not_yet_collected"]
StatState = Literal["value", "not_provided", "unknown", "not_yet_collected", "unavailable"]


class InvalidSourceIdError(ValueError):
    pass


@dataclass(frozen=True)
class VideoStatistics:
    """``None`` on a field means YouTube did not provide it (for example hidden likes)."""

    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None


@dataclass(frozen=True)
class VideoRecord:
    video_id: str
    channel_id: str | None = None
    channel_title: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    duration_iso: str | None = None
    category_id: str | None = None
    default_language: str | None = None
    thumbnail_url: str | None = None
    embeddable: bool | None = None
    # None = the statistics part was not requested/returned in this fetch.
    statistics: VideoStatistics | None = None


@dataclass(frozen=True)
class ChannelRecord:
    channel_id: str
    title: str | None = None
    uploads_playlist_id: str | None = None


@dataclass(frozen=True)
class StatValue:
    state: StatState
    value: int | None = None

    @property
    def label(self) -> str:
        if self.state == "value":
            return str(self.value)
        if self.state == "not_yet_collected":
            return "Not yet collected"
        if self.state == "unknown":
            return "Unknown"
        return "Unavailable"  # not provided by YouTube, inaccessible or expired


@dataclass(frozen=True)
class VideoView:
    """What derived views and exports may show. Expired data never reaches this object."""

    video_id: str
    state: VideoState
    title: str | None = None
    channel_id: str | None = None
    channel_title: str | None = None
    published_at_utc: str | None = None
    duration_iso: str | None = None
    thumbnail_url: str | None = None
    embeddable: bool | None = None
    source_endpoint: str | None = None
    fetched_at_utc: str | None = None
    expires_at_utc: str | None = None
    last_refresh_outcome: str | None = None
    title_changed_at_utc: str | None = None
    thumbnail_changed_at_utc: str | None = None
    views: StatValue = field(default_factory=lambda: StatValue("unavailable"))
    likes: StatValue = field(default_factory=lambda: StatValue("unavailable"))
    comments: StatValue = field(default_factory=lambda: StatValue("unavailable"))

    @property
    def is_eligible_reference(self) -> bool:
        return self.state == "available"


@dataclass
class RefreshResult:
    refreshed: list[str] = field(default_factory=list)
    inserted: list[str] = field(default_factory=list)
    skipped_fresh: list[str] = field(default_factory=list)
    inaccessible: list[str] = field(default_factory=list)
    purged_on_touch: list[str] = field(default_factory=list)
    not_returned_unknown: list[str] = field(default_factory=list)
    titles_changed: list[str] = field(default_factory=list)
    thumbnails_changed: list[str] = field(default_factory=list)


_VIDEO_COLS = (
    "channel_id, channel_title, title, published_at_utc, duration_iso, category_id, "
    "default_language, thumbnail_url, embeddable"
)


class SourceRepository:
    def __init__(self, db: Database, policy: RetentionPolicy | None = None) -> None:
        self.db = db
        self.policy = policy or RetentionPolicy()

    # ---------- validation ----------
    def _check_id(self, source_id: str) -> None:
        if self.db.dataset == "synthetic":
            if ":" not in source_id:
                raise InvalidSourceIdError(
                    f"fixture IDs must contain ':' so they cannot look real: {source_id!r}"
                )
        elif not _LIVE_ID_RE.match(source_id):
            raise InvalidSourceIdError(f"not a YouTube-shaped ID: {source_id!r}")

    def _check_endpoint(self, endpoint: str) -> None:
        if (self.db.dataset == "synthetic") != (endpoint == "fixture"):
            raise ValueError(f"endpoint {endpoint!r} is not allowed in the {self.db.dataset} DB")

    @staticmethod
    def _check_batch(ids: Sequence[str]) -> None:
        if len(ids) > MAX_IDS_PER_BATCH:
            raise ValueError(f"at most {MAX_IDS_PER_BATCH} IDs per batch")
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate IDs in one batch")

    # ---------- writes ----------
    def _write_video(self, rec: VideoRecord, endpoint: str, now: datetime) -> tuple[bool, bool]:
        """Insert or fully replace one video and its stats.

        Returns (title_changed, thumbnail_changed) versus the previous unexpired row.
        """
        conn = self.db.conn
        ts = to_db_ts(now)
        due, expires = (to_db_ts(t) for t in self.policy.deadlines(now))
        old = conn.execute(
            "SELECT title, thumbnail_url, title_changed_at_utc, thumbnail_changed_at_utc, "
            "access_state FROM videos WHERE video_id = ? AND expires_at_utc > ?",
            (rec.video_id, ts),
        ).fetchone()
        title_changed = bool(
            old
            and old["access_state"] == "available"
            and old["title"] is not None
            and rec.title is not None
            and old["title"] != rec.title
        )
        thumb_changed = bool(
            old
            and old["access_state"] == "available"
            and old["thumbnail_url"] is not None
            and rec.thumbnail_url is not None
            and old["thumbnail_url"] != rec.thumbnail_url
        )
        title_changed_at = ts if title_changed else (old["title_changed_at_utc"] if old else None)
        thumb_changed_at = (
            ts if thumb_changed else (old["thumbnail_changed_at_utc"] if old else None)
        )
        values = (
            rec.video_id,
            self.db.lineage_class,
            rec.channel_id,
            rec.channel_title,
            rec.title,
            to_db_ts(rec.published_at) if rec.published_at else None,
            rec.duration_iso,
            rec.category_id,
            rec.default_language,
            rec.thumbnail_url,
            None if rec.embeddable is None else int(rec.embeddable),
            endpoint,
            ts,
            due,
            expires,
            ts,
            title_changed_at,
            thumb_changed_at,
        )
        conn.execute(
            f"""
            INSERT INTO videos (video_id, lineage_class, {_VIDEO_COLS}, access_state,
                source_endpoint, fetched_at_utc, refresh_due_at_utc, expires_at_utc,
                last_refresh_attempt_utc, last_refresh_outcome, last_error_code,
                title_changed_at_utc, thumbnail_changed_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?, ?, 'ok', NULL, ?, ?)
            ON CONFLICT (video_id) DO UPDATE SET
                lineage_class = excluded.lineage_class,
                channel_id = excluded.channel_id, channel_title = excluded.channel_title,
                title = excluded.title, published_at_utc = excluded.published_at_utc,
                duration_iso = excluded.duration_iso, category_id = excluded.category_id,
                default_language = excluded.default_language,
                thumbnail_url = excluded.thumbnail_url, embeddable = excluded.embeddable,
                access_state = 'available', source_endpoint = excluded.source_endpoint,
                fetched_at_utc = excluded.fetched_at_utc,
                refresh_due_at_utc = excluded.refresh_due_at_utc,
                expires_at_utc = excluded.expires_at_utc,
                last_refresh_attempt_utc = excluded.last_refresh_attempt_utc,
                last_refresh_outcome = 'ok', last_error_code = NULL,
                title_changed_at_utc = excluded.title_changed_at_utc,
                thumbnail_changed_at_utc = excluded.thumbnail_changed_at_utc
            """,  # noqa: S608 (column list is a module constant)
            values,
        )
        if rec.statistics is not None:
            s = rec.statistics
            conn.execute(
                """
                INSERT INTO public_statistics_current (video_id, lineage_class, view_count,
                    like_count, comment_count, source_endpoint, fetched_at_utc, expires_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (video_id) DO UPDATE SET
                    view_count = excluded.view_count, like_count = excluded.like_count,
                    comment_count = excluded.comment_count,
                    source_endpoint = excluded.source_endpoint,
                    fetched_at_utc = excluded.fetched_at_utc,
                    expires_at_utc = excluded.expires_at_utc
                """,
                (
                    rec.video_id,
                    self.db.lineage_class,
                    s.view_count,
                    s.like_count,
                    s.comment_count,
                    endpoint if endpoint == "fixture" else "videos.list",
                    ts,
                    expires,
                ),
            )
        return title_changed, thumb_changed

    def apply_videos_list(
        self,
        requested_ids: Sequence[str],
        returned: Sequence[VideoRecord],
        endpoint: VideoEndpoint = "videos.list",
    ) -> RefreshResult:
        """Apply one ``videos.list`` batch: replace returned rows, tombstone missing ones.

        An ID that was requested but not returned is deleted, private or removed. Its
        metadata and statistics are dropped immediately; a tombstone with no API fields
        stays until the original expiry so derived views can say "Unavailable".
        """
        if endpoint not in ("videos.list", "fixture"):
            raise ValueError("only videos.list (or fixture) can detect inaccessible videos")
        self._check_endpoint(endpoint)
        self._check_batch(requested_ids)
        for vid in requested_ids:
            self._check_id(vid)
        by_id = {r.video_id: r for r in returned}
        if len(by_id) != len(returned) or not set(by_id) <= set(requested_ids):
            raise ValueError("returned records must be unique and a subset of requested IDs")

        now = self.db.clock.now()
        ts = to_db_ts(now)
        result = RefreshResult()
        with self.db.transaction() as conn:
            for vid in requested_ids:
                existing = conn.execute(
                    "SELECT expires_at_utc FROM videos WHERE video_id = ?", (vid,)
                ).fetchone()
                if existing is not None and existing["expires_at_utc"] <= ts:
                    # Lapsed rows are purged (with redaction) before anything new is written,
                    # so expired associations never ride along with fresh data.
                    purge_videos(self.db, [vid])
                    result.purged_on_touch.append(vid)
                    existing = None
                if vid in by_id:
                    t_changed, th_changed = self._write_video(by_id[vid], endpoint, now)
                    (result.refreshed if existing else result.inserted).append(vid)
                    if t_changed:
                        result.titles_changed.append(vid)
                    if th_changed:
                        result.thumbnails_changed.append(vid)
                elif existing is None:
                    if vid not in result.purged_on_touch:
                        result.not_returned_unknown.append(vid)
                else:
                    conn.execute("DELETE FROM public_statistics_current WHERE video_id = ?", (vid,))
                    conn.execute(
                        """
                        UPDATE videos SET access_state = 'inaccessible',
                            channel_id = NULL, channel_title = NULL, title = NULL,
                            published_at_utc = NULL, duration_iso = NULL, category_id = NULL,
                            default_language = NULL, thumbnail_url = NULL, embeddable = NULL,
                            refresh_due_at_utc = expires_at_utc,
                            last_refresh_attempt_utc = ?, last_refresh_outcome = 'not_returned',
                            last_error_code = NULL
                        WHERE video_id = ?
                        """,
                        (ts, vid),
                    )
                    result.inaccessible.append(vid)
        return result

    def store_discovered(
        self, records: Sequence[VideoRecord], endpoint: VideoEndpoint
    ) -> RefreshResult:
        """Store candidates seen in search/playlist results.

        A fresh existing row is left untouched: overwriting part of it would silently
        extend the lifetime of fields fetched earlier. Missing or expired rows are written.
        """
        self._check_endpoint(endpoint)
        ids = [r.video_id for r in records]
        self._check_batch(ids)
        for vid in ids:
            self._check_id(vid)
        now = self.db.clock.now()
        ts = to_db_ts(now)
        result = RefreshResult()
        with self.db.transaction() as conn:
            for rec in records:
                fresh = conn.execute(
                    "SELECT 1 FROM videos WHERE video_id = ? AND expires_at_utc > ?",
                    (rec.video_id, ts),
                ).fetchone()
                if fresh:
                    result.skipped_fresh.append(rec.video_id)
                    continue
                if conn.execute(
                    "SELECT 1 FROM videos WHERE video_id = ?", (rec.video_id,)
                ).fetchone():
                    purge_videos(self.db, [rec.video_id])  # expired: purge before rewriting
                self._write_video(rec, endpoint, now)
                result.inserted.append(rec.video_id)
        return result

    def record_refresh_error(self, video_ids: Sequence[str], error_code: str) -> int:
        """Mark an API error. Data, fetch time and expiry are left unchanged on purpose:
        a failed refresh never extends the life of what is stored."""
        self._check_batch(video_ids)
        ts = to_db_ts(self.db.clock.now())
        with self.db.transaction() as conn:
            marks = ",".join("?" * len(video_ids))
            cur = conn.execute(
                f"UPDATE videos SET last_refresh_attempt_utc = ?, "  # noqa: S608
                f"last_refresh_outcome = 'api_error', last_error_code = ? "
                f"WHERE video_id IN ({marks})",
                (ts, error_code[:64], *video_ids),
            )
            return cur.rowcount

    def apply_channels_list(
        self,
        requested_ids: Sequence[str],
        returned: Sequence[ChannelRecord],
        endpoint: ChannelEndpoint = "channels.list",
    ) -> RefreshResult:
        self._check_endpoint(endpoint)
        self._check_batch(requested_ids)
        for cid in requested_ids:
            self._check_id(cid)
        by_id = {r.channel_id: r for r in returned}
        if len(by_id) != len(returned) or not set(by_id) <= set(requested_ids):
            raise ValueError("returned records must be unique and a subset of requested IDs")
        now = self.db.clock.now()
        ts = to_db_ts(now)
        due, expires = (to_db_ts(t) for t in self.policy.deadlines(now))
        result = RefreshResult()
        with self.db.transaction() as conn:
            for cid in requested_ids:
                existing = conn.execute(
                    "SELECT expires_at_utc FROM channels WHERE channel_id = ?", (cid,)
                ).fetchone()
                rec = by_id.get(cid)
                if rec is not None:
                    conn.execute(
                        """
                        INSERT INTO channels (channel_id, lineage_class, access_state, title,
                            uploads_playlist_id, source_endpoint, fetched_at_utc,
                            refresh_due_at_utc, expires_at_utc, last_refresh_attempt_utc,
                            last_refresh_outcome, last_error_code)
                        VALUES (?, ?, 'available', ?, ?, ?, ?, ?, ?, ?, 'ok', NULL)
                        ON CONFLICT (channel_id) DO UPDATE SET
                            access_state = 'available', title = excluded.title,
                            uploads_playlist_id = excluded.uploads_playlist_id,
                            source_endpoint = excluded.source_endpoint,
                            fetched_at_utc = excluded.fetched_at_utc,
                            refresh_due_at_utc = excluded.refresh_due_at_utc,
                            expires_at_utc = excluded.expires_at_utc,
                            last_refresh_attempt_utc = excluded.last_refresh_attempt_utc,
                            last_refresh_outcome = 'ok', last_error_code = NULL
                        """,
                        (
                            cid,
                            self.db.lineage_class,
                            rec.title,
                            rec.uploads_playlist_id,
                            endpoint,
                            ts,
                            due,
                            expires,
                            ts,
                        ),
                    )
                    (result.refreshed if existing else result.inserted).append(cid)
                elif existing is None:
                    result.not_returned_unknown.append(cid)
                elif existing["expires_at_utc"] <= ts:
                    conn.execute("DELETE FROM channels WHERE channel_id = ?", (cid,))
                    result.purged_on_touch.append(cid)
                elif endpoint in ("channels.list", "fixture"):
                    conn.execute(
                        "UPDATE channels SET access_state = 'inaccessible', title = NULL, "
                        "uploads_playlist_id = NULL, refresh_due_at_utc = expires_at_utc, "
                        "last_refresh_attempt_utc = ?, last_refresh_outcome = 'not_returned' "
                        "WHERE channel_id = ?",
                        (ts, cid),
                    )
                    result.inaccessible.append(cid)
        return result

    # ---------- reads (never return expired data) ----------
    def due_for_refresh(self, limit: int = MAX_IDS_PER_BATCH) -> list[str]:
        """Available, unexpired videos whose proactive refresh time has arrived."""
        limit = max(1, min(limit, MAX_LIST_LIMIT))
        ts = to_db_ts(self.db.clock.now())
        rows = self.db.conn.execute(
            "SELECT video_id FROM videos WHERE access_state = 'available' "
            "AND refresh_due_at_utc <= ? AND expires_at_utc > ? "
            "ORDER BY expires_at_utc, video_id LIMIT ?",
            (ts, ts, limit),
        )
        return [r[0] for r in rows]

    def get_video(self, video_id: str) -> VideoView:
        ts = to_db_ts(self.db.clock.now())
        row = self.db.conn.execute(
            f"""
            SELECT v.video_id, v.access_state, {_VIDEO_COLS}, v.source_endpoint,
                   v.fetched_at_utc, v.expires_at_utc, v.last_refresh_outcome,
                   v.title_changed_at_utc, v.thumbnail_changed_at_utc,
                   s.video_id AS stats_present, s.view_count, s.like_count, s.comment_count
            FROM videos v
            LEFT JOIN public_statistics_current s
                   ON s.video_id = v.video_id AND s.expires_at_utc > :now
            WHERE v.video_id = :id AND v.expires_at_utc > :now
            """,  # noqa: S608 (column list is a module constant)
            {"id": video_id, "now": ts},
        ).fetchone()
        if row is None:
            exists = self.db.conn.execute(
                "SELECT 1 FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()
            return VideoView(video_id, "expired" if exists else "not_yet_collected")
        if row["access_state"] == "inaccessible":
            return VideoView(
                video_id,
                "inaccessible",
                fetched_at_utc=row["fetched_at_utc"],
                expires_at_utc=row["expires_at_utc"],
                last_refresh_outcome=row["last_refresh_outcome"],
            )

        def stat(value: int | None) -> StatValue:
            if row["stats_present"] is None:
                if row["last_refresh_outcome"] == "api_error":
                    return StatValue("unknown")
                return StatValue("not_yet_collected")
            return StatValue("not_provided") if value is None else StatValue("value", value)

        return VideoView(
            video_id=video_id,
            state="available",
            title=row["title"],
            channel_id=row["channel_id"],
            channel_title=row["channel_title"],
            published_at_utc=row["published_at_utc"],
            duration_iso=row["duration_iso"],
            thumbnail_url=row["thumbnail_url"],
            embeddable=None if row["embeddable"] is None else bool(row["embeddable"]),
            source_endpoint=row["source_endpoint"],
            fetched_at_utc=row["fetched_at_utc"],
            expires_at_utc=row["expires_at_utc"],
            last_refresh_outcome=row["last_refresh_outcome"],
            title_changed_at_utc=row["title_changed_at_utc"],
            thumbnail_changed_at_utc=row["thumbnail_changed_at_utc"],
            views=stat(row["view_count"]),
            likes=stat(row["like_count"]),
            comments=stat(row["comment_count"]),
        )

    def list_video_ids(self, limit: int = 50, offset: int = 0) -> list[str]:
        """Bounded page of unexpired video IDs (available first)."""
        limit = max(1, min(limit, MAX_LIST_LIMIT))
        ts = to_db_ts(self.db.clock.now())
        rows = self.db.conn.execute(
            "SELECT video_id FROM videos WHERE expires_at_utc > ? "
            "ORDER BY access_state, video_id LIMIT ? OFFSET ?",
            (ts, limit, max(0, offset)),
        )
        return [r[0] for r in rows]

    def get_channel_title(self, channel_id: str) -> str | None:
        ts = to_db_ts(self.db.clock.now())
        row = self.db.conn.execute(
            "SELECT title FROM channels WHERE channel_id = ? AND expires_at_utc > ? "
            "AND access_state = 'available'",
            (channel_id, ts),
        ).fetchone()
        return row["title"] if row else None

    def health(self) -> dict[str, int]:
        ts = to_db_ts(self.db.clock.now())
        row = self.db.conn.execute(
            """
            SELECT
              coalesce(sum(expires_at_utc > :now AND access_state = 'available'), 0) AS fresh,
              coalesce(sum(expires_at_utc > :now AND access_state = 'available'
                           AND refresh_due_at_utc <= :now), 0) AS due,
              coalesce(sum(expires_at_utc > :now AND access_state = 'inaccessible'), 0) AS gone,
              coalesce(sum(expires_at_utc > :now AND last_refresh_outcome = 'api_error'), 0)
                  AS errors,
              coalesce(sum(expires_at_utc <= :now), 0) AS expired
            FROM videos
            """,
            {"now": ts},
        ).fetchone()
        return {
            "videos_fresh": int(row["fresh"]),
            "videos_due_for_refresh": int(row["due"]),
            "videos_inaccessible": int(row["gone"]),
            "videos_last_refresh_api_error": int(row["errors"]),
            "videos_expired_awaiting_purge": int(row["expired"]),
        }


def parse_db_ts(value: str | None) -> datetime | None:
    return from_db_ts(value) if value else None
