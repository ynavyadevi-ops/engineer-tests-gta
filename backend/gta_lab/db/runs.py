"""Sample-selection repository: discovery runs, hits and eligibility reviews.

Hits and reviews point at stored videos and are purged with them at expiry. Duplicate
hits inside one run (same video, path and query) are counted, not stored twice.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ..clock import to_db_ts
from .connection import Database
from .sources import MAX_LIST_LIMIT

RunMode = Literal["plan", "run", "resume"]
RunStatus = Literal["planned", "running", "paused", "completed", "failed"]
DiscoveryPath = Literal[
    "search_relevance",
    "search_date",
    "search_popularity",
    "uploads_playlist",
    "curated_playlist",
    "fixture",
]
MAX_HITS_PER_BATCH = 500


@dataclass(frozen=True)
class Hit:
    video_id: str
    discovery_path: DiscoveryPath
    query_text: str = ""
    page_index: int = 0
    era: str | None = None
    locale: str | None = None


@dataclass(frozen=True)
class HitBatchResult:
    inserted: int
    duplicates: int


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: str
    hits: int
    distinct_videos: int
    duplicate_hits: int
    unavailable_results: int
    accepted: int
    excluded: int
    needs_review: int
    unreviewed: int


class RunRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_run(
        self,
        mode: RunMode,
        manifest_version: str | None = None,
        resumed_from: str | None = None,
        run_id: str | None = None,
    ) -> str:
        run_id = run_id or uuid.uuid4().hex
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO discovery_runs (run_id, dataset, mode, status, manifest_version, "
                "resumed_from_run_id, started_at_utc) VALUES (?, ?, ?, 'planned', ?, ?, ?)",
                (
                    run_id,
                    self.db.dataset,
                    mode,
                    manifest_version,
                    resumed_from,
                    to_db_ts(self.db.clock.now()),
                ),
            )
        return run_id

    def set_status(self, run_id: str, status: RunStatus) -> None:
        finished = to_db_ts(self.db.clock.now()) if status in ("completed", "failed") else None
        with self.db.transaction() as conn:
            if not conn.execute(
                "UPDATE discovery_runs SET status = ?, finished_at_utc = ? WHERE run_id = ?",
                (status, finished, run_id),
            ).rowcount:
                raise KeyError(run_id)

    def record_hits(self, run_id: str, hits: Sequence[Hit]) -> HitBatchResult:
        """Record one bounded batch atomically. Every video must already be stored."""
        if len(hits) > MAX_HITS_PER_BATCH:
            raise ValueError(f"at most {MAX_HITS_PER_BATCH} hits per batch")
        now = to_db_ts(self.db.clock.now())
        inserted = 0
        with self.db.transaction() as conn:
            for h in hits:
                cur = conn.execute(
                    "INSERT INTO discovery_hits (run_id, video_id, discovery_path, query_text, "
                    "page_index, era, locale, discovered_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (run_id, video_id, discovery_path, query_text) DO NOTHING",
                    (
                        run_id,
                        h.video_id,
                        h.discovery_path,
                        h.query_text,
                        h.page_index,
                        h.era,
                        h.locale,
                        now,
                    ),
                )
                inserted += cur.rowcount
            duplicates = len(hits) - inserted
            conn.execute(
                "UPDATE discovery_runs SET duplicate_hits = duplicate_hits + ? WHERE run_id = ?",
                (duplicates, run_id),
            )
        return HitBatchResult(inserted=inserted, duplicates=duplicates)

    def record_unavailable(self, run_id: str, count: int) -> None:
        if count < 0:
            raise ValueError("count must be >= 0")
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE discovery_runs SET unavailable_results = unavailable_results + ? "
                "WHERE run_id = ?",
                (count, run_id),
            )

    def summary(self, run_id: str) -> RunSummary:
        conn = self.db.conn
        run = conn.execute("SELECT * FROM discovery_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            raise KeyError(run_id)
        row = conn.execute(
            """
            SELECT count(*) AS hits, count(DISTINCT h.video_id) AS distinct_videos,
                   count(DISTINCT CASE WHEN e.state = 'accepted' THEN h.video_id END) AS acc,
                   count(DISTINCT CASE WHEN e.state = 'excluded' THEN h.video_id END) AS exc,
                   count(DISTINCT CASE WHEN e.state = 'needs_review' THEN h.video_id END) AS nr,
                   count(DISTINCT CASE WHEN e.state IS NULL THEN h.video_id END) AS unrev
            FROM discovery_hits h LEFT JOIN eligibility_reviews e ON e.video_id = h.video_id
            WHERE h.run_id = ?
            """,
            (run_id,),
        ).fetchone()
        return RunSummary(
            run_id=run_id,
            status=run["status"],
            hits=row["hits"],
            distinct_videos=row["distinct_videos"],
            duplicate_hits=run["duplicate_hits"],
            unavailable_results=run["unavailable_results"],
            accepted=row["acc"],
            excluded=row["exc"],
            needs_review=row["nr"],
            unreviewed=row["unrev"],
        )

    # ---------- eligibility reviews ----------
    def set_eligibility(
        self,
        video_id: str,
        state: Literal["accepted", "excluded", "needs_review"],
        reviewer: str,
        qualification: Literal["human_verified", "source_qualified"],
        reasons: str | None = None,
        base_game: str = "unknown",
        offline_confirmed: str = "uncertain",
        format_verification: str = "unknown",
    ) -> None:
        now = to_db_ts(self.db.clock.now())
        with self.db.transaction() as conn:
            ok = conn.execute(
                "SELECT 1 FROM videos WHERE video_id = ? AND expires_at_utc > ? "
                "AND access_state = 'available'",
                (video_id, now),
            ).fetchone()
            if not ok:
                raise ValueError(f"{video_id!r} is not an available, unexpired video")
            conn.execute(
                """
                INSERT INTO eligibility_reviews (video_id, state, reasons, base_game,
                    offline_confirmed, format_verification, qualification, reviewer,
                    reviewed_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (video_id) DO UPDATE SET
                    state = excluded.state, reasons = excluded.reasons,
                    base_game = excluded.base_game,
                    offline_confirmed = excluded.offline_confirmed,
                    format_verification = excluded.format_verification,
                    qualification = excluded.qualification, reviewer = excluded.reviewer,
                    reviewed_at_utc = excluded.reviewed_at_utc
                """,
                (
                    video_id,
                    state,
                    reasons,
                    base_game,
                    offline_confirmed,
                    format_verification,
                    qualification,
                    reviewer,
                    now,
                ),
            )

    def review_queue(self, limit: int = 50) -> list[str]:
        """Unexpired, available videos that are unreviewed or need review (bounded)."""
        limit = max(1, min(limit, MAX_LIST_LIMIT))
        now = to_db_ts(self.db.clock.now())
        rows = self.db.conn.execute(
            "SELECT v.video_id FROM videos v LEFT JOIN eligibility_reviews e "
            "ON e.video_id = v.video_id WHERE v.expires_at_utc > ? AND v.access_state = "
            "'available' AND (e.state IS NULL OR e.state = 'needs_review') "
            "ORDER BY v.video_id LIMIT ?",
            (now, limit),
        )
        return [r[0] for r in rows]
