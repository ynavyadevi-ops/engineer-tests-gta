"""SQLite connection, transactions and fixture/live isolation.

* WAL, foreign keys on, bounded busy timeout, ``secure_delete`` so purged API data is
  overwritten in the file rather than left in free pages.
* A database file is bound to one dataset (``synthetic`` or ``live``) the first time it is
  opened; reopening it as the other dataset raises ``DatasetMismatchError``.
* A live database is refused inside a cloud-synced folder: a synced copy is an
  uncontrolled backup of API data that would outlive the 30-day retention window.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from ..clock import Clock, SystemClock
from ..config import Settings, looks_cloud_synced
from .migrate import MigrationResult, migrate

Dataset = Literal["synthetic", "live"]
BUSY_TIMEOUT_MS = 5000


class DatasetMismatchError(RuntimeError):
    pass


class UnsafeLocationError(RuntimeError):
    pass


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA secure_delete = ON")
    return conn


class Database:
    """An open, migrated database bound to one dataset and one clock."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        dataset: Dataset,
        clock: Clock,
        migration: MigrationResult,
    ) -> None:
        self.conn = conn
        self.dataset: Dataset = dataset
        self.clock = clock
        self.migration = migration
        self._depth = 0

    @property
    def lineage_class(self) -> str:
        return "synthetic" if self.dataset == "synthetic" else "youtube_api"

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """All-or-nothing write block. Nested calls become savepoints."""
        if self._depth == 0:
            self.conn.execute("BEGIN IMMEDIATE")
            begin, commit, rollback = None, "COMMIT", "ROLLBACK"
        else:
            name = f"sp_{self._depth}"
            begin = f"SAVEPOINT {name}"
            commit, rollback = f"RELEASE {name}", f"ROLLBACK TO {name}; RELEASE {name}"
            self.conn.execute(begin)
        self._depth += 1
        try:
            yield self.conn
        except BaseException:
            self._depth -= 1
            for stmt in rollback.split("; "):
                self.conn.execute(stmt)
            raise
        else:
            self._depth -= 1
            self.conn.execute(commit)

    def checkpoint(self) -> None:
        """Fold the WAL into the main file and truncate it (used after purges)."""
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def schema_version(self) -> int:
        row = self.conn.execute("SELECT max(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def open_database(
    path: Path,
    dataset: Dataset,
    clock: Clock | None = None,
    migrations_dir: Path | None = None,
) -> Database:
    if dataset not in ("synthetic", "live"):
        raise ValueError(f"unknown dataset: {dataset!r}")
    if dataset == "live" and looks_cloud_synced(path):
        raise UnsafeLocationError(
            "refusing to open the live database inside a cloud-synced folder; "
            "set GTA_LAB_DATA_DIR to a local, non-synced path"
        )
    clock = clock or SystemClock()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        result = migrate(conn, migrations_dir, clock)
        row = conn.execute("SELECT value FROM db_meta WHERE key = 'dataset'").fetchone()
        if row is None:
            conn.execute("INSERT INTO db_meta (key, value) VALUES ('dataset', ?)", (dataset,))
        elif row[0] != dataset:
            raise DatasetMismatchError(
                f"{path.name} holds {row[0]} data and cannot be opened as {dataset}"
            )
    except BaseException:
        conn.close()
        raise
    return Database(conn, dataset, clock, result)


def dataset_for(settings: Settings) -> Dataset:
    return "live" if settings.mode == "live" else "synthetic"


def open_for_settings(settings: Settings, clock: Clock | None = None) -> Database:
    return open_database(settings.active_db_path, dataset_for(settings), clock)
