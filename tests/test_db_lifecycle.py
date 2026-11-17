"""Fake-clock retention: proactive refresh, API errors, expiry suppression, purge,
inaccessible videos, changed titles/thumbnails, expired references in views and exports."""

from __future__ import annotations

from pathlib import Path

import pytest

from gta_lab.clock import FakeClock
from gta_lab.db import (
    BriefDraft,
    EditorialRepository,
    Hit,
    RetentionPolicy,
    RunRepository,
    SourceRepository,
    purge_expired,
)
from gta_lab.db.retention import REDACTION_MARK

from .db_support import T0, fx, open_synthetic, rec


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


def count(db, table: str) -> int:  # type: ignore[no-untyped-def]
    return int(db.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608


def test_retention_policy_caps_at_30_days() -> None:
    with pytest.raises(ValueError, match="approval"):
        RetentionPolicy(max_age_days=31)
    with pytest.raises(ValueError):
        RetentionPolicy(max_age_days=30, refresh_lead_days=30)
    due, expires = RetentionPolicy().deadlines(T0)
    assert (expires - T0).days == 30 and (expires - due).days == 5


def test_lineage_and_deadlines_are_stored(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        SourceRepository(db).apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        row = db.conn.execute("SELECT * FROM videos").fetchone()
        assert row["source_endpoint"] == "fixture"
        assert row["lineage_class"] == "synthetic"
        assert row["fetched_at_utc"] == "2026-01-01T12:00:00Z"
        assert row["refresh_due_at_utc"] == "2026-01-26T12:00:00Z"
        assert row["expires_at_utc"] == "2026-01-31T12:00:00Z"
        stats = db.conn.execute("SELECT * FROM public_statistics_current").fetchone()
        assert stats["expires_at_utc"] == "2026-01-31T12:00:00Z"


def test_proactive_refresh_window(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        repo = SourceRepository(db)
        repo.apply_videos_list([fx(1), fx(2)], [rec(1), rec(2)], endpoint="fixture")
        clock.advance(days=24)
        assert repo.due_for_refresh() == []
        clock.advance(days=1)  # day 25: inside the 5-day lead window, before expiry
        assert repo.due_for_refresh() == [fx(1), fx(2)]
        repo.apply_videos_list([fx(1)], [rec(1, views=150)], endpoint="fixture")
        assert repo.due_for_refresh() == [fx(2)]


def test_refresh_replaces_current_stats_without_history(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        repo = SourceRepository(db)
        repo.apply_videos_list([fx(1)], [rec(1, views=100)], endpoint="fixture")
        clock.advance(days=26)
        out = repo.apply_videos_list([fx(1)], [rec(1, views=250)], endpoint="fixture")
        assert out.refreshed == [fx(1)]
        assert count(db, "public_statistics_current") == 1
        assert count(db, "videos") == 1
        view = repo.get_video(fx(1))
        assert view.views.value == 250
        assert view.fetched_at_utc == "2026-01-27T12:00:00Z"
        assert view.expires_at_utc == "2026-02-26T12:00:00Z"


def test_failed_refresh_never_extends_life_and_expired_data_is_suppressed(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        repo = SourceRepository(db)
        repo.apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        clock.advance(days=26)
        assert repo.record_refresh_error([fx(1)], "quotaExceeded") == 1
        view = repo.get_video(fx(1))
        assert view.state == "available" and view.last_refresh_outcome == "api_error"
        assert view.expires_at_utc == "2026-01-31T12:00:00Z"  # unchanged

        clock.advance(days=4, hours=1)  # past expiry; refresh still failing; no purge yet
        repo.record_refresh_error([fx(1)], "backendError")
        stale = repo.get_video(fx(1))
        assert stale.state == "expired"
        assert stale.title is None and stale.channel_title is None
        assert stale.views.state == "unavailable" and stale.views.label == "Unavailable"
        assert repo.list_video_ids() == []
        assert repo.due_for_refresh() == []
        health = repo.health()
        assert health["videos_fresh"] == 0 and health["videos_expired_awaiting_purge"] == 1


def test_purge_removes_expired_data_and_associations_keeps_authored_text(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        runs = RunRepository(db)
        ed = EditorialRepository(db)
        src.apply_videos_list([fx(1), fx(2)], [rec(1), rec(2)], endpoint="fixture")
        run_id = runs.create_run("run")
        runs.record_hits(run_id, [Hit(fx(1), "fixture", "q"), Hit(fx(2), "fixture", "q")])
        runs.set_eligibility(fx(1), "accepted", "editor", "human_verified")
        own = ed.add_note("own_gameplay", "Traffic reacts after the lane block.", "editor")
        linked = ed.add_note(
            "idea", "Retest the ramp at night.", "editor", source_video_ids=[fx(1)]
        )

        # Day 20: fx(2) keeps being refreshed, fx(1) does not.
        clock.advance(days=20)
        src.apply_videos_list([fx(2)], [rec(2)], endpoint="fixture")
        # Day 30 + 1h: fx(1) expired, fx(2) fresh until day 50.
        clock.advance(days=10, hours=1)
        # Simulate a note that picked up copied text after it was written (bypassing guards).
        db.conn.execute(
            "UPDATE editor_notes SET body = body || ' Like in Synthetic test video number 1 "
            "(fixture:vid-001).' WHERE note_id = ?",
            (linked,),
        )
        report = purge_expired(db)
        assert report.videos_purged == 1
        assert report.statistics_purged == 1
        assert report.discovery_hits_removed == 1
        assert report.eligibility_reviews_removed == 1
        assert report.note_refs_removed == 1
        assert report.notes_redacted == 1

        assert src.get_video(fx(1)).state == "not_yet_collected"  # gone entirely
        assert src.get_video(fx(2)).state == "available"
        assert count(db, "discovery_hits") == 1
        assert count(db, "eligibility_reviews") == 0
        assert count(db, "note_source_refs") == 0
        note = ed.get_note(linked)
        assert "Retest the ramp at night." in note.body
        assert (
            "Synthetic test video number 1" not in note.body and "fixture:vid-001" not in note.body
        )
        assert REDACTION_MARK in note.body and note.redacted_at_utc is not None
        assert ed.get_note(own).body == "Traffic reacts after the lane block."
        assert ed.get_note(own).redacted_at_utc is None
        # Purge is idempotent.
        assert purge_expired(db).videos_purged == 0
        # WAL folded and truncated so purged pages do not linger in the -wal file.
        wal = Path(str(tmp_path / "db dir" / "demo.sqlite3") + "-wal")
        assert not wal.exists() or wal.stat().st_size == 0


def test_inaccessible_video_tombstone(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        ed = EditorialRepository(db)
        src.apply_videos_list([fx(1), fx(2)], [rec(1), rec(2)], endpoint="fixture")
        brief = ed.create_brief(
            BriefDraft("Blocked lane test", "systems_myth_tests", "long_form"),
            source_video_ids=[fx(1), fx(2)],
        )
        clock.advance(days=26)
        # fx(1) deleted/private: requested but not returned.
        out = src.apply_videos_list([fx(1), fx(2)], [rec(2)], endpoint="fixture")
        assert out.inaccessible == [fx(1)] and out.refreshed == [fx(2)]
        view = src.get_video(fx(1))
        assert view.state == "inaccessible"
        assert view.title is None and view.thumbnail_url is None
        assert view.views.label == "Unavailable"
        row = db.conn.execute("SELECT * FROM videos WHERE video_id = ?", (fx(1),)).fetchone()
        assert row["title"] is None and row["channel_title"] is None
        assert row["last_refresh_outcome"] == "not_returned"
        stats = db.conn.execute(
            "SELECT count(*) FROM public_statistics_current WHERE video_id = ?", (fx(1),)
        ).fetchone()[0]
        assert stats == 0
        assert fx(1) not in src.due_for_refresh(200)

        refs = {r.video_id: r for r in ed.get_brief(brief).refs}
        assert refs[fx(1)].state == "inaccessible" and refs[fx(1)].link is None
        assert refs[fx(2)].link is not None
        export = ed.export_brief_text(brief)
        assert fx(1) not in export and "1 source reference(s) no longer available" in export

        # Tombstone lives only until the original expiry, then is purged.
        clock.advance(days=4, hours=1)
        assert purge_expired(db).videos_purged == 1
        assert src.get_video(fx(1)).state == "not_yet_collected"
        assert [r.video_id for r in ed.get_brief(brief).refs] == [fx(2)]


def test_inaccessible_video_that_returns_becomes_available(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        src.apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        src.apply_videos_list([fx(1)], [], endpoint="fixture")
        assert src.get_video(fx(1)).state == "inaccessible"
        clock.advance(days=1)
        src.apply_videos_list([fx(1)], [rec(1, views=5)], endpoint="fixture")
        view = src.get_video(fx(1))
        assert view.state == "available" and view.views.value == 5
        assert view.title_changed_at_utc is None  # no prior title to compare with


def test_unknown_id_not_returned_is_not_stored(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        out = SourceRepository(db).apply_videos_list([fx(9)], [], endpoint="fixture")
        assert out.not_returned_unknown == [fx(9)]
        assert count(db, "videos") == 0


def test_title_and_thumbnail_changes_are_flagged_not_archived(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        src.apply_videos_list([fx(1)], [rec(1, title="Old synthetic title")], endpoint="fixture")
        clock.advance(days=3)
        out = src.apply_videos_list(
            [fx(1)],
            [rec(1, title="New synthetic title", thumb="https://example.invalid/new.jpg")],
            endpoint="fixture",
        )
        assert out.titles_changed == [fx(1)] and out.thumbnails_changed == [fx(1)]
        view = src.get_video(fx(1))
        assert view.title == "New synthetic title"
        assert view.title_changed_at_utc == "2026-01-04T12:00:00Z"
        assert view.thumbnail_changed_at_utc == "2026-01-04T12:00:00Z"
        # The old title is not kept anywhere (no history archive).
        dump = "\n".join(db.conn.iterdump())
        assert "Old synthetic title" not in dump


def test_refreshing_a_lapsed_row_purges_it_first(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        ed = EditorialRepository(db)
        src.apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        note = ed.add_note("idea", "Night ramp idea.", "editor", source_video_ids=[fx(1)])
        clock.advance(days=31)  # expired, purge job has not run
        out = src.apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        assert out.purged_on_touch == [fx(1)] and out.inserted == [fx(1)]
        assert ed.get_note(note).refs == []  # expired association did not ride along


def test_discovery_never_extends_a_fresh_rows_lifetime(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        src.apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        clock.advance(days=10)
        out = src.store_discovered([rec(1), rec(2)], endpoint="fixture")
        assert out.skipped_fresh == [fx(1)] and out.inserted == [fx(2)]
        assert src.get_video(fx(1)).expires_at_utc == "2026-01-31T12:00:00Z"


def test_expired_references_are_hidden_in_note_views_before_purge(
    tmp_path: Path, clock: FakeClock
) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        ed = EditorialRepository(db)
        src.apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        note = ed.add_note("idea", "Check the bridge.", "editor", source_video_ids=[fx(1)])
        clock.advance(days=30)
        view = ed.get_note(note)
        assert view.refs == [] and view.refs_no_longer_available == 1


def test_brief_redaction_on_purge(tmp_path: Path, clock: FakeClock) -> None:
    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        ed = EditorialRepository(db)
        src.apply_videos_list([fx(1)], [rec(1)], endpoint="fixture")
        brief = ed.create_brief(
            BriefDraft(
                "Bridge physics test",
                "systems_myth_tests",
                "short",
                payoff_beat="The car clears the gap.",
            ),
            source_video_ids=[fx(1)],
        )
        db.conn.execute(
            "UPDATE briefs SET original_angle = 'Unlike Synthetic Channel One, test both sides.' "
            "WHERE brief_id = ?",
            (brief,),
        )
        clock.advance(days=31)
        report = purge_expired(db)
        assert report.briefs_redacted == 1 and report.brief_refs_removed == 1
        d = ed.get_brief(brief).draft
        assert "Synthetic Channel One" not in (d.original_angle or "")
        assert d.payoff_beat == "The car clears the gap."
        assert d.working_title == "Bridge physics test"


def test_channels_follow_the_same_lifecycle(tmp_path: Path, clock: FakeClock) -> None:
    from gta_lab.db import ChannelRecord

    with open_synthetic(tmp_path, clock) as db:
        src = SourceRepository(db)
        cid = "fixture:chan-001"
        src.apply_channels_list([cid], [ChannelRecord(cid, "Synthetic Channel One")], "fixture")
        assert src.get_channel_title(cid) == "Synthetic Channel One"
        src.apply_channels_list([cid], [], "fixture")
        assert src.get_channel_title(cid) is None
        clock.advance(days=31)
        assert purge_expired(db).channels_purged == 1
