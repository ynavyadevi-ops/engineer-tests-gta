"""Fresh and repeat migration, failure rollback, tamper detection, schema rules."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from gta_lab.clock import FakeClock
from gta_lab.db import MigrationError, migrate, open_database
from gta_lab.db.connection import connect
from gta_lab.db.migrate import default_migrations_dir, discover

from .db_support import T0, open_synthetic

EXPECTED_TABLES = {
    "schema_migrations",
    "db_meta",
    "policy_capabilities",
    "channels",
    "videos",
    "public_statistics_current",
    "playlist_sources",
    "discovery_runs",
    "discovery_hits",
    "eligibility_reviews",
    "editor_notes",
    "note_source_refs",
    "briefs",
    "brief_source_refs",
    "plans",
    "calendar_slots",
    "publishing_log",
    "owner_metric_entries",
}


def tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


@pytest.fixture
def mig_dir(tmp_path: Path) -> Path:
    target = tmp_path / "migrations copy"
    shutil.copytree(default_migrations_dir(), target)
    return target


def test_fresh_migration_creates_full_schema(tmp_path: Path) -> None:
    with open_synthetic(tmp_path) as db:
        assert db.migration.applied == (1, 2, 3, 4)
        assert db.schema_version() == 4
        assert tables(db.conn) == EXPECTED_TABLES
        caps = db.conn.execute("SELECT capability, status FROM policy_capabilities").fetchall()
        assert len(caps) == 4 and {c["status"] for c in caps} == {"off"}


def test_repeat_migration_is_a_noop(tmp_path: Path) -> None:
    open_synthetic(tmp_path).close()
    with open_synthetic(tmp_path) as db:
        assert db.migration.applied == ()
        assert db.schema_version() == 4
        assert migrate(db.conn).applied == ()  # third run on the same connection
        n = db.conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        assert n == 4
        caps = db.conn.execute("SELECT count(*) FROM policy_capabilities").fetchone()[0]
        assert caps == 4  # seed rows not duplicated


def test_connection_pragmas(tmp_path: Path) -> None:
    with open_synthetic(tmp_path) as db:
        assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
        assert db.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_failed_migration_rolls_back_completely(tmp_path: Path, mig_dir: Path) -> None:
    (mig_dir / "0005_broken.sql").write_text(
        "CREATE TABLE half_done (x INTEGER);\nINSERT INTO no_such_table VALUES (1);\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "broken.sqlite3")
    with pytest.raises(MigrationError, match="0005_broken"):
        migrate(conn, mig_dir, FakeClock(T0))
    assert "half_done" not in tables(conn)
    assert conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 4
    assert not conn.in_transaction
    # Fix the file and retry: it applies cleanly.
    (mig_dir / "0005_broken.sql").write_text("CREATE TABLE half_done (x INTEGER);\n")
    assert migrate(conn, mig_dir, FakeClock(T0)).applied == (5,)
    conn.close()


def test_changed_applied_migration_is_rejected(tmp_path: Path, mig_dir: Path) -> None:
    conn = connect(tmp_path / "t.sqlite3")
    migrate(conn, mig_dir)
    path = mig_dir / "0001_foundation.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="changed after it was applied"):
        migrate(conn, mig_dir)
    conn.close()


def test_crlf_checkout_keeps_the_same_checksum(tmp_path: Path, mig_dir: Path) -> None:
    conn = connect(tmp_path / "t.sqlite3")
    migrate(conn, mig_dir)
    for f in mig_dir.glob("*.sql"):
        f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert migrate(conn, mig_dir).applied == ()
    conn.close()


def test_database_newer_than_code_is_rejected(tmp_path: Path, mig_dir: Path) -> None:
    (mig_dir / "0005_extra.sql").write_text("CREATE TABLE extra (x INTEGER);\n")
    conn = connect(tmp_path / "t.sqlite3")
    migrate(conn, mig_dir)
    (mig_dir / "0005_extra.sql").unlink()
    with pytest.raises(MigrationError, match="does not know"):
        migrate(conn, mig_dir)
    conn.close()


def test_gaps_and_bad_names_are_rejected(mig_dir: Path) -> None:
    (mig_dir / "0007_gap.sql").write_text("SELECT 1;\n")
    with pytest.raises(MigrationError, match="contiguous"):
        discover(mig_dir)
    (mig_dir / "0007_gap.sql").unlink()
    (mig_dir / "5_bad name.sql").write_text("SELECT 1;\n")
    with pytest.raises(MigrationError, match="unexpected migration file name"):
        discover(mig_dir)


def test_no_raw_response_body_columns(tmp_path: Path) -> None:
    banned = ("raw", "response", "payload", "json", "snippet", "description", "comment_text")
    with open_synthetic(tmp_path) as db:
        for table in tables(db.conn):
            for col in db.conn.execute(f"PRAGMA table_info({table})"):
                name = col["name"].lower()
                assert not any(b in name for b in banned), f"{table}.{name}"


def test_schema_enforces_30_day_maximum_retention(tmp_path: Path) -> None:
    with open_synthetic(tmp_path) as db, pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO videos (video_id, lineage_class, source_endpoint, fetched_at_utc, "
            "refresh_due_at_utc, expires_at_utc) VALUES ('fixture:x', 'synthetic', 'fixture', "
            "'2026-01-01T00:00:00Z', '2026-01-20T00:00:00Z', '2026-02-01T00:00:00Z')"
        )


def test_schema_rejects_non_utc_timestamp_text(tmp_path: Path) -> None:
    with open_synthetic(tmp_path) as db, pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO videos (video_id, lineage_class, source_endpoint, fetched_at_utc, "
            "refresh_due_at_utc, expires_at_utc) VALUES ('fixture:x', 'synthetic', 'fixture', "
            "'2026-01-01 00:00:00+05:30', '2026-01-20T00:00:00Z', '2026-01-25T00:00:00Z')"
        )


def test_capability_cannot_turn_on_without_proof(tmp_path: Path) -> None:
    with open_synthetic(tmp_path) as db, pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "UPDATE policy_capabilities SET status = 'on' WHERE capability = 'cohort_analytics'"
        )


def test_open_database_creates_parent_folder_with_spaces(tmp_path: Path) -> None:
    path = tmp_path / "a folder" / "with spaces" / "x.sqlite3"
    open_database(path, "synthetic", FakeClock(T0)).close()
    assert path.is_file()
