"""Fixture/live isolation: separate files, bound datasets, ID shapes, lineage triggers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gta_lab.clock import FakeClock
from gta_lab.config import load_settings
from gta_lab.db import (
    DatasetMismatchError,
    InvalidSourceIdError,
    SourceRepository,
    UnsafeLocationError,
    VideoRecord,
    open_database,
    open_for_settings,
)

from .db_support import T0, rec


def test_demo_and_live_use_separate_files() -> None:
    demo = load_settings(mode="demo")
    live = load_settings(mode="live")
    assert demo.active_db_path != live.active_db_path
    assert demo.active_db_path.parent != live.active_db_path.parent


def test_open_for_settings_binds_the_dataset_to_the_mode() -> None:
    with open_for_settings(load_settings(mode="demo"), FakeClock(T0)) as db:
        assert db.dataset == "synthetic"
        assert db.lineage_class == "synthetic"
    with open_for_settings(load_settings(mode="live"), FakeClock(T0)) as db:
        assert db.dataset == "live"
        assert db.lineage_class == "youtube_api"


def test_fixture_db_cannot_be_reopened_as_live_and_vice_versa(tmp_path: Path) -> None:
    demo, live = tmp_path / "demo.sqlite3", tmp_path / "live.sqlite3"
    open_database(demo, "synthetic").close()
    open_database(live, "live").close()
    with pytest.raises(DatasetMismatchError):
        open_database(demo, "live")
    with pytest.raises(DatasetMismatchError):
        open_database(live, "synthetic")


def test_dataset_marker_is_immutable(tmp_path: Path) -> None:
    with open_database(tmp_path / "d.sqlite3", "synthetic") as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.conn.execute("UPDATE db_meta SET value = 'live' WHERE key = 'dataset'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.conn.execute("DELETE FROM db_meta WHERE key = 'dataset'")


def test_fixture_db_rejects_real_shaped_ids(tmp_path: Path) -> None:
    with open_database(tmp_path / "d.sqlite3", "synthetic", FakeClock(T0)) as db:
        repo = SourceRepository(db)
        with pytest.raises(InvalidSourceIdError):
            repo.apply_videos_list(["placeholder-live-01"], [], endpoint="fixture")
        with pytest.raises(ValueError, match="not allowed"):
            repo.apply_videos_list([rec(1).video_id], [rec(1)], endpoint="videos.list")


def test_live_db_rejects_fixture_ids_and_fixture_endpoint(tmp_path: Path) -> None:
    with open_database(tmp_path / "l.sqlite3", "live", FakeClock(T0)) as db:
        repo = SourceRepository(db)
        with pytest.raises(InvalidSourceIdError):
            repo.apply_videos_list(["fixture:vid-001"], [], endpoint="videos.list")
        with pytest.raises(ValueError, match="not allowed"):
            repo.apply_videos_list(["placeholder-live-01"], [], endpoint="fixture")


def test_live_db_triggers_block_synthetic_rows_even_via_raw_sql(tmp_path: Path) -> None:
    with open_database(tmp_path / "l.sqlite3", "live", FakeClock(T0)) as db:
        with pytest.raises(sqlite3.IntegrityError, match="db_meta.dataset"):
            db.conn.execute(
                "INSERT INTO videos (video_id, lineage_class, source_endpoint, fetched_at_utc, "
                "refresh_due_at_utc, expires_at_utc) VALUES ('fixture:x', 'synthetic', "
                "'fixture', '2026-01-01T00:00:00Z', '2026-01-20T00:00:00Z', "
                "'2026-01-25T00:00:00Z')"
            )
        with pytest.raises(sqlite3.IntegrityError, match="db_meta.dataset"):
            db.conn.execute(
                "INSERT INTO discovery_runs (run_id, dataset, mode, started_at_utc) "
                "VALUES ('r1', 'synthetic', 'plan', '2026-01-01T00:00:00Z')"
            )


def test_fixture_db_triggers_block_youtube_api_rows(tmp_path: Path) -> None:
    db = open_database(tmp_path / "d.sqlite3", "synthetic", FakeClock(T0))
    with db, pytest.raises(sqlite3.IntegrityError, match="db_meta.dataset"):
        db.conn.execute(
            "INSERT INTO videos (video_id, lineage_class, source_endpoint, fetched_at_utc, "
            "refresh_due_at_utc, expires_at_utc) VALUES ('placeholder-live-01', 'youtube_api', "
            "'videos.list', '2026-01-01T00:00:00Z', '2026-01-20T00:00:00Z', "
            "'2026-01-25T00:00:00Z')"
        )


def test_live_db_is_refused_inside_a_cloud_synced_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced = tmp_path / "Synced Root"
    monkeypatch.setenv("OneDrive", str(synced))
    with pytest.raises(UnsafeLocationError):
        open_database(synced / "data" / "live.sqlite3", "live")
    assert not (synced / "data" / "live.sqlite3").exists()
    # Synthetic fixtures are allowed (they hold no API data).
    open_database(synced / "data" / "demo.sqlite3", "synthetic").close()


def test_live_db_accepts_youtube_shaped_ids(tmp_path: Path) -> None:
    with open_database(tmp_path / "l.sqlite3", "live", FakeClock(T0)) as db:
        repo = SourceRepository(db)
        # Not 11 chars, so it can never be a real video ID; no network is involved.
        out = repo.apply_videos_list(
            ["placeholder-live-01"], [VideoRecord("placeholder-live-01", title="t")]
        )
        assert out.inserted == ["placeholder-live-01"]
        row = db.conn.execute("SELECT lineage_class, source_endpoint FROM videos").fetchone()
        assert tuple(row) == ("youtube_api", "videos.list")
