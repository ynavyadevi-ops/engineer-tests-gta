"""Standard-mode retention (docs/YOUTUBE_POLICY.md).

* ``RetentionPolicy`` turns a fetch time into a refresh-due time and a hard expiry that is
  never more than 30 calendar days later. Extended retention is approval-only and not
  configurable here.
* ``purge_expired`` deletes expired API-derived rows (videos, channels, statistics) in one
  transaction. Foreign keys cascade the purge to associations: discovery hits, eligibility
  reviews, note and brief source references. Before the references go, copied API
  fragments (current title, channel title, video ID) are redacted from the associated
  note and brief text, so only independently authored text survives.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from ..clock import to_db_ts
from .connection import Database

MAX_RETENTION_DAYS = 30
REDACTION_MARK = "[removed: expired YouTube data]"
MIN_REDACT_LEN = 4
PURGE_CHUNK = 500

BRIEF_TEXT_COLUMNS: tuple[str, ...] = (
    "working_title",
    "alternate_title",
    "viewer_question",
    "original_angle",
    "first_frame",
    "cold_open",
    "shot_checklist",
    "verification_plan",
    "thumbnail_hypothesis_a",
    "thumbnail_hypothesis_b",
    "cover_design",
    "payoff_beat",
    "fallback_plan",
    "reel_adaptation",
    "success_measure",
)


@dataclass(frozen=True)
class RetentionPolicy:
    max_age_days: int = MAX_RETENTION_DAYS
    refresh_lead_days: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.max_age_days <= MAX_RETENTION_DAYS:
            raise ValueError(
                f"max_age_days must be 1..{MAX_RETENTION_DAYS} in standard mode "
                "(longer retention needs written YouTube approval)"
            )
        if not 0 <= self.refresh_lead_days < self.max_age_days:
            raise ValueError("refresh_lead_days must be >= 0 and < max_age_days")

    def deadlines(self, fetched_at: datetime) -> tuple[datetime, datetime]:
        expires = fetched_at + timedelta(days=self.max_age_days)
        due = expires - timedelta(days=self.refresh_lead_days)
        return due, expires


@dataclass(frozen=True)
class PurgeReport:
    videos_purged: int = 0
    channels_purged: int = 0
    statistics_purged: int = 0
    discovery_hits_removed: int = 0
    eligibility_reviews_removed: int = 0
    note_refs_removed: int = 0
    brief_refs_removed: int = 0
    notes_redacted: int = 0
    briefs_redacted: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def redact(text: str | None, fragments: Iterable[str]) -> str | None:
    """Replace every case-insensitive occurrence of each fragment with the redaction mark."""
    if text is None:
        return None
    result = text
    for fragment in sorted({f for f in fragments if f}, key=len, reverse=True):
        if len(fragment) < MIN_REDACT_LEN:
            continue
        result = re.sub(re.escape(fragment), REDACTION_MARK, result, flags=re.IGNORECASE)
    return result


def _chunks(items: Sequence[str], size: int = PURGE_CHUNK) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _count(db: Database, table: str, ids: Sequence[str]) -> int:
    marks = ",".join("?" * len(ids))
    sql = f"SELECT count(*) FROM {table} WHERE video_id IN ({marks})"  # noqa: S608 (fixed table names)
    return int(db.conn.execute(sql, tuple(ids)).fetchone()[0])


def purge_videos(db: Database, video_ids: Sequence[str]) -> PurgeReport:
    """Delete the given videos now, redacting copied fragments from associated text first.

    Used by ``purge_expired`` and when a refresh touches a row that has already expired.
    """
    now = to_db_ts(db.clock.now())
    totals = dict.fromkeys(PurgeReport.__dataclass_fields__, 0)
    with db.transaction() as conn:
        fragments: dict[str, list[str]] = {}
        for chunk in _chunks(list(dict.fromkeys(video_ids))):
            marks = ",".join("?" * len(chunk))
            for r in conn.execute(
                f"SELECT video_id, title, channel_title FROM videos "  # noqa: S608
                f"WHERE video_id IN ({marks})",
                tuple(chunk),
            ):
                fragments[r["video_id"]] = [r["video_id"], r["title"], r["channel_title"]]
        ids = list(fragments)

        for chunk in _chunks(ids):
            marks = ",".join("?" * len(chunk))
            totals["discovery_hits_removed"] += _count(db, "discovery_hits", chunk)
            totals["eligibility_reviews_removed"] += _count(db, "eligibility_reviews", chunk)
            totals["note_refs_removed"] += _count(db, "note_source_refs", chunk)
            totals["brief_refs_removed"] += _count(db, "brief_source_refs", chunk)
            totals["statistics_purged"] += _count(db, "public_statistics_current", chunk)

            # Redact copied fragments from text associated with the purged videos.
            note_rows = conn.execute(
                f"SELECT n.note_id, n.body, group_concat(r.video_id, char(31)) AS vids "  # noqa: S608
                f"FROM editor_notes n JOIN note_source_refs r ON r.note_id = n.note_id "
                f"WHERE r.video_id IN ({marks}) GROUP BY n.note_id",
                tuple(chunk),
            ).fetchall()
            for row in note_rows:
                frags = [f for vid in row["vids"].split("") for f in fragments[vid]]
                new_body = redact(row["body"], frags)
                if new_body != row["body"]:
                    conn.execute(
                        "UPDATE editor_notes SET body = ?, redacted_at_utc = ?, updated_at_utc = ? "
                        "WHERE note_id = ?",
                        (new_body, now, now, row["note_id"]),
                    )
                    totals["notes_redacted"] += 1

            cols = ", ".join(f"b.{c}" for c in BRIEF_TEXT_COLUMNS)
            brief_rows = conn.execute(
                f"SELECT b.brief_id, {cols}, group_concat(r.video_id, char(31)) AS vids "  # noqa: S608
                f"FROM briefs b JOIN brief_source_refs r ON r.brief_id = b.brief_id "
                f"WHERE r.video_id IN ({marks}) GROUP BY b.brief_id",
                tuple(chunk),
            ).fetchall()
            for row in brief_rows:
                frags = [f for vid in row["vids"].split("") for f in fragments[vid]]
                changes = {}
                for c in BRIEF_TEXT_COLUMNS:
                    redacted = redact(row[c], frags)
                    if redacted != row[c]:
                        changes[c] = redacted
                if changes:
                    sets = ", ".join(f"{c} = ?" for c in changes)
                    conn.execute(
                        f"UPDATE briefs SET {sets}, redacted_at_utc = ?, updated_at_utc = ? "  # noqa: S608
                        "WHERE brief_id = ?",
                        (*changes.values(), now, now, row["brief_id"]),
                    )
                    totals["briefs_redacted"] += 1

            totals["videos_purged"] += conn.execute(
                f"DELETE FROM videos WHERE video_id IN ({marks})",  # noqa: S608
                tuple(chunk),
            ).rowcount
    return PurgeReport(**totals)


def purge_expired(db: Database) -> PurgeReport:
    """Purge every expired API-derived row, then fold and truncate the WAL."""
    now = to_db_ts(db.clock.now())
    with db.transaction() as conn:
        rows = conn.execute("SELECT video_id FROM videos WHERE expires_at_utc <= ?", (now,))
        expired = [r[0] for r in rows]
        totals = purge_videos(db, expired).as_dict()
        # Statistics can expire on their own schedule (e.g. stats from an older fetch).
        totals["statistics_purged"] += conn.execute(
            "DELETE FROM public_statistics_current WHERE expires_at_utc <= ?", (now,)
        ).rowcount
        totals["channels_purged"] += conn.execute(
            "DELETE FROM channels WHERE expires_at_utc <= ?", (now,)
        ).rowcount
    db.checkpoint()
    return PurgeReport(**totals)
