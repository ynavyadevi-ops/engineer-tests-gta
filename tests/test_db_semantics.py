"""Null semantics, duplicates, transaction rollback and editorial/own-channel rules."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from gta_lab.clock import FakeClock
from gta_lab.db import (
    BriefDraft,
    CopiedApiDataError,
    EditorialRepository,
    Hit,
    IneligibleSourceError,
    LedgerRepository,
    OwnerMetrics,
    PlanRepository,
    RunRepository,
    SourceRepository,
)

from .db_support import T0, fx, open_synthetic, rec


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


# ---------- null semantics ----------


def test_hidden_counts_stay_null_never_zero(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        src.apply_videos_list([fx(1)], [rec(1, views=0, likes=None, comments=None)], "fixture")
        row = db.conn.execute("SELECT * FROM public_statistics_current").fetchone()
        assert row["view_count"] == 0
        assert row["like_count"] is None and row["comment_count"] is None
        view = src.get_video(fx(1))
        assert view.views.state == "value" and view.views.label == "0"
        assert view.likes.state == "not_provided" and view.likes.label == "Unavailable"


def test_stat_states_distinguish_not_collected_unknown_and_missing(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        assert src.get_video(fx(1)).state == "not_yet_collected"
        # Metadata without the statistics part: not yet collected.
        src.apply_videos_list([fx(1)], [rec(1, stats=False)], "fixture")
        view = src.get_video(fx(1))
        assert view.views.state == "not_yet_collected"
        assert view.views.label == "Not yet collected"
        # An API error while no stats exist: unknown (retry later), not "missing".
        src.record_refresh_error([fx(1)], "backendError")
        assert src.get_video(fx(1)).views.state == "unknown"
        assert src.get_video(fx(1)).views.label == "Unknown"


def test_optional_metadata_stays_null(tmp_path: Path, clock: FakeClock) -> None:
    from gta_lab.db import VideoRecord

    with open_synthetic(tmp_path, clock) as db:
        SourceRepository(db).apply_videos_list([fx(1)], [VideoRecord(fx(1))], "fixture")
        row = db.conn.execute("SELECT * FROM videos").fetchone()
        for col in ("title", "duration_iso", "embeddable", "default_language", "category_id"):
            assert row[col] is None


def test_manual_studio_checkpoint_blanks_stay_null(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        ledger = LedgerRepository(db)
        entry = ledger.log_release("youtube_short", title_variant="My own title A")
        ledger.add_checkpoint(entry, "24h", OwnerMetrics(views=None, likes=3))
        row = db.conn.execute("SELECT * FROM owner_metric_entries").fetchone()
        assert row["views"] is None and row["likes"] == 3


# ---------- duplicates ----------


def test_repeated_upsert_keeps_one_row(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        for _ in range(3):
            src.apply_videos_list([fx(1)], [rec(1)], "fixture")
        assert db.conn.execute("SELECT count(*) FROM videos").fetchone()[0] == 1


def test_duplicate_ids_in_one_batch_and_oversized_batches_are_rejected(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        with pytest.raises(ValueError, match="duplicate"):
            src.apply_videos_list([fx(1), fx(1)], [rec(1)], "fixture")
        with pytest.raises(ValueError, match="at most 50"):
            src.apply_videos_list([fx(i) for i in range(51)], [], "fixture")
        with pytest.raises(ValueError, match="subset"):
            src.apply_videos_list([fx(1)], [rec(2)], "fixture")


def test_duplicate_hits_are_counted_not_stored(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        SourceRepository(db).apply_videos_list([fx(1), fx(2)], [rec(1), rec(2)], "fixture")
        runs = RunRepository(db)
        run = runs.create_run("run", manifest_version="m-synthetic-1")
        first = runs.record_hits(run, [Hit(fx(1), "fixture", "q1"), Hit(fx(2), "fixture", "q1")])
        again = runs.record_hits(
            run,
            [Hit(fx(1), "fixture", "q1"), Hit(fx(1), "fixture", "q2")],  # dup + new path
        )
        assert (first.inserted, first.duplicates) == (2, 0)
        assert (again.inserted, again.duplicates) == (1, 1)
        runs.set_eligibility(fx(1), "accepted", "editor", "human_verified")
        runs.set_eligibility(fx(2), "excluded", "editor", "source_qualified", reasons="online")
        summary = runs.summary(run)
        assert summary.hits == 3 and summary.distinct_videos == 2
        assert summary.duplicate_hits == 1
        assert (summary.accepted, summary.excluded, summary.unreviewed) == (1, 1, 0)
        # A second run may see the same video again (cross-run is not a duplicate row).
        run2 = runs.create_run("resume", resumed_from=run)
        assert runs.record_hits(run2, [Hit(fx(1), "fixture", "q1")]).inserted == 1


def test_excluded_review_needs_a_reason(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        SourceRepository(db).apply_videos_list([fx(1)], [rec(1)], "fixture")
        with pytest.raises(sqlite3.IntegrityError):
            RunRepository(db).set_eligibility(fx(1), "excluded", "editor", "human_verified")


# ---------- transaction rollback ----------


def test_batch_with_one_bad_record_rolls_back_entirely(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        with pytest.raises(sqlite3.IntegrityError):
            src.apply_videos_list([fx(1), fx(2)], [rec(1), rec(2, views=-5)], "fixture")
        assert db.conn.execute("SELECT count(*) FROM videos").fetchone()[0] == 0
        assert db.conn.execute("SELECT count(*) FROM public_statistics_current").fetchone()[0] == 0
        assert not db.conn.in_transaction


def test_hit_batch_with_unknown_video_rolls_back(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        SourceRepository(db).apply_videos_list([fx(1)], [rec(1)], "fixture")
        runs = RunRepository(db)
        run = runs.create_run("run")
        with pytest.raises(sqlite3.IntegrityError):
            runs.record_hits(run, [Hit(fx(1), "fixture"), Hit(fx(99), "fixture")])
        assert db.conn.execute("SELECT count(*) FROM discovery_hits").fetchone()[0] == 0
        assert runs.summary(run).duplicate_hits == 0


def test_nested_transaction_rolls_back_inner_only(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        plans = PlanRepository(db)
        with db.transaction():
            outer = plans.create_plan("Outer plan", date(2026, 3, 1))
            with pytest.raises(sqlite3.IntegrityError), db.transaction():
                plans.add_slot(outer, 31, "youtube_short", "film")  # day 31 is invalid
            plans.add_slot(outer, 1, "youtube_short", "film")
        assert [s.day_index for s in plans.slots(outer)] == [1]


def test_outer_failure_rolls_back_everything(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        plans = PlanRepository(db)
        with pytest.raises(RuntimeError), db.transaction():
            plans.create_plan("Doomed plan", date(2026, 3, 1))
            raise RuntimeError("boom")
        assert db.conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 0


# ---------- editorial rules ----------


def test_copied_api_text_is_refused(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        SourceRepository(db).apply_videos_list([fx(1)], [rec(1)], "fixture")
        ed = EditorialRepository(db)
        with pytest.raises(CopiedApiDataError):
            ed.add_note(
                "idea",
                "Redo synthetic TEST video number 1 better",
                "editor",
                source_video_ids=[fx(1)],
            )
        with pytest.raises(CopiedApiDataError):
            ed.create_brief(
                BriefDraft("Synthetic Channel One style test", "systems_myth_tests", "short"),
                source_video_ids=[fx(1)],
            )
        assert db.conn.execute("SELECT count(*) FROM editor_notes").fetchone()[0] == 0
        note = ed.add_note("idea", "My own angle on ramps.", "editor", source_video_ids=[fx(1)])
        with pytest.raises(CopiedApiDataError):
            ed.update_note_body(note, "Synthetic test video number 1 again")


def test_references_must_be_eligible_when_written(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        ed = EditorialRepository(db)
        with pytest.raises(IneligibleSourceError, match="not_yet_collected"):
            ed.add_note("idea", "x idea", "editor", source_video_ids=[fx(1)])
        src.apply_videos_list([fx(1)], [rec(1)], "fixture")
        src.apply_videos_list([fx(1)], [], "fixture")  # now inaccessible
        with pytest.raises(IneligibleSourceError, match="inaccessible"):
            ed.add_note("idea", "x idea", "editor", source_video_ids=[fx(1)])


def test_watched_requires_a_human_watch_time(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        ed = EditorialRepository(db)
        with pytest.raises(ValueError, match="human"):
            ed.add_note("watched_observation", "Cold open is 3 s.", "editor")
        with pytest.raises(ValueError):
            ed.add_note("idea", "x", "editor", watched_at=T0)
        nid = ed.add_note("watched_observation", "Cold open is 3 s.", "editor", watched_at=T0)
        assert ed.get_note(nid).watched_at_utc == "2026-01-01T12:00:00Z"


def test_plan_export_has_no_youtube_metadata(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        SourceRepository(db).apply_videos_list([fx(1)], [rec(1)], "fixture")
        ed = EditorialRepository(db)
        brief = ed.create_brief(
            BriefDraft("Ramp myth test", "systems_myth_tests", "short"), source_video_ids=[fx(1)]
        )
        plans = PlanRepository(db)
        plan = plans.create_plan("Launch month", date(2026, 3, 1))
        plans.add_slot(plan, 1, "youtube_short", "film", brief_id=brief, pinned=True)
        plans.add_slot(plan, 2, "none", "rest")
        text = plans.export_plan_text(plan)
        assert "Day  1 | film | youtube_short | brief: Ramp myth test | pinned" in text
        assert "Synthetic test video" not in text and "fixture:vid" not in text
        brief_text = ed.export_brief_text(brief)
        assert "Synthetic test video" not in brief_text
        assert "https://www.youtube.com/watch?v=fixture:vid-001" in brief_text
        assert "100" not in brief_text  # no metrics
        # Rebuild keeps pinned slots.
        assert plans.clear_unpinned(plan) == 1
        assert [s.day_index for s in plans.slots(plan)] == [1]


def test_instagram_has_no_metrics_and_verdicts_need_rationale(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        ledger = LedgerRepository(db)
        reel = ledger.log_release("instagram_reel")
        with pytest.raises(sqlite3.IntegrityError, match="Instagram"):
            ledger.add_checkpoint(reel, "24h", OwnerMetrics(views=1))
        short = ledger.log_release("youtube_short")
        with pytest.raises(sqlite3.IntegrityError):
            ledger.set_verdict(short, "retest", "  ")
        ledger.set_verdict(short, "retest", "Variant and pacing co-varied.")
        with pytest.raises(sqlite3.IntegrityError):  # one entry per checkpoint
            ledger.add_checkpoint(short, "7d", OwnerMetrics())
            ledger.add_checkpoint(short, "7d", OwnerMetrics())
