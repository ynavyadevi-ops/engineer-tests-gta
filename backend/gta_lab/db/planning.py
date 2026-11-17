"""Plans, calendar slots, the own-channel publishing ledger and manual Studio checkpoints.

Plan exports contain original calendar and brief text only, never YouTube metadata or
metrics. Own-channel rows are never mixed with third-party statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from ..clock import to_db_ts
from .connection import Database

Lane = Literal["youtube_long_form", "youtube_short", "instagram_reel", "none"]
Action = Literal["film", "edit", "publish", "review", "rest", "buffer"]


@dataclass(frozen=True)
class Slot:
    slot_id: int
    day_index: int
    lane: str
    action: str
    brief_id: int | None
    pinned: bool
    status: str
    slot_note: str | None


@dataclass(frozen=True)
class OwnerMetrics:
    """Manual Studio numbers. ``None`` = left blank (not zero)."""

    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    avg_view_duration_seconds: int | None = None
    impressions_ctr_percent: float | None = None


class PlanRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _now(self) -> str:
        return to_db_ts(self.db.clock.now())

    def create_plan(
        self,
        title: str,
        start_date: date,
        timezone: str = "Asia/Kolkata",
        weekly_budget_hours: float = 11.0,
    ) -> int:
        now = self._now()
        with self.db.transaction() as conn:
            plan_id = conn.execute(
                "INSERT INTO plans (title, start_date, timezone, weekly_budget_hours, "
                "created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
                (title, start_date.isoformat(), timezone, weekly_budget_hours, now, now),
            ).lastrowid
        if plan_id is None:
            raise RuntimeError("insert returned no row id")
        return int(plan_id)

    def add_slot(
        self,
        plan_id: int,
        day_index: int,
        lane: Lane,
        action: Action,
        brief_id: int | None = None,
        pinned: bool = False,
        slot_note: str | None = None,
    ) -> int:
        now = self._now()
        with self.db.transaction() as conn:
            slot_id = conn.execute(
                "INSERT INTO calendar_slots (plan_id, day_index, lane, action, brief_id, pinned, "
                "slot_note, created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (plan_id, day_index, lane, action, brief_id, int(pinned), slot_note, now, now),
            ).lastrowid
        if slot_id is None:
            raise RuntimeError("insert returned no row id")
        return int(slot_id)

    def set_pinned(self, slot_id: int, pinned: bool) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE calendar_slots SET pinned = ?, updated_at_utc = ? WHERE slot_id = ?",
                (int(pinned), self._now(), slot_id),
            )

    def clear_unpinned(self, plan_id: int) -> int:
        """Remove unpinned, still-planned slots before a rebuild. Pinned slots survive."""
        with self.db.transaction() as conn:
            return conn.execute(
                "DELETE FROM calendar_slots "
                "WHERE plan_id = ? AND pinned = 0 AND status = 'planned'",
                (plan_id,),
            ).rowcount

    def slots(self, plan_id: int) -> list[Slot]:
        rows = self.db.conn.execute(
            "SELECT * FROM calendar_slots WHERE plan_id = ? ORDER BY day_index, slot_id",
            (plan_id,),
        )
        return [
            Slot(
                r["slot_id"],
                r["day_index"],
                r["lane"],
                r["action"],
                r["brief_id"],
                bool(r["pinned"]),
                r["status"],
                r["slot_note"],
            )
            for r in rows
        ]

    def export_plan_text(self, plan_id: int) -> str:
        plan = self.db.conn.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,)).fetchone()
        if plan is None:
            raise KeyError(plan_id)
        lines = [
            f"# {plan['title']}",
            f"Start date: {plan['start_date']} ({plan['timezone']}), "
            f"weekly budget {plan['weekly_budget_hours']:g} h",
        ]
        rows = self.db.conn.execute(
            "SELECT s.day_index, s.lane, s.action, s.pinned, s.status, s.slot_note, "
            "b.working_title FROM calendar_slots s LEFT JOIN briefs b ON b.brief_id = s.brief_id "
            "WHERE s.plan_id = ? ORDER BY s.day_index, s.slot_id",
            (plan_id,),
        )
        for r in rows:
            parts = [f"Day {r['day_index']:>2}", r["action"]]
            if r["lane"] != "none":
                parts.append(r["lane"])
            if r["working_title"]:
                parts.append(f"brief: {r['working_title']}")
            if r["slot_note"]:
                parts.append(r["slot_note"])
            if r["pinned"]:
                parts.append("pinned")
            if r["status"] != "planned":
                parts.append(r["status"])
            lines.append(" | ".join(parts))
        return "\n".join(lines) + "\n"


class LedgerRepository:
    """Own-channel publishing ledger (ownership class ``own_channel``)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def log_release(
        self,
        lane: Literal["youtube_long_form", "youtube_short", "instagram_reel"],
        brief_id: int | None = None,
        title_variant: str | None = None,
        hypothesis: str | None = None,
    ) -> int:
        now = to_db_ts(self.db.clock.now())
        with self.db.transaction() as conn:
            entry_id = conn.execute(
                "INSERT INTO publishing_log (lane, brief_id, title_variant, hypothesis, "
                "created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
                (lane, brief_id, title_variant, hypothesis, now, now),
            ).lastrowid
        if entry_id is None:
            raise RuntimeError("insert returned no row id")
        return int(entry_id)

    def set_verdict(
        self, entry_id: int, verdict: Literal["promising", "retest", "retire"], rationale: str
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE publishing_log SET verdict = ?, verdict_rationale = ?, updated_at_utc = ? "
                "WHERE entry_id = ?",
                (verdict, rationale, to_db_ts(self.db.clock.now()), entry_id),
            )

    def add_checkpoint(
        self, entry_id: int, checkpoint: Literal["24h", "7d"], metrics: OwnerMetrics
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO owner_metric_entries (entry_id, checkpoint, views, likes, comments, "
                "avg_view_duration_seconds, impressions_ctr_percent, entered_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    checkpoint,
                    metrics.views,
                    metrics.likes,
                    metrics.comments,
                    metrics.avg_view_duration_seconds,
                    metrics.impressions_ctr_percent,
                    to_db_ts(self.db.clock.now()),
                ),
            )
