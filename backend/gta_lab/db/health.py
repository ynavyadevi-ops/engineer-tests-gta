"""Summarised, read-only data-health counts for ``/api/status`` and ``db status``.

Opens the database read-only and never creates, migrates or purges it. Returns counts
only: no rows, titles or IDs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..clock import Clock, SystemClock
from .connection import Database
from .migrate import MigrationResult
from .sources import SourceRepository


def read_health(path: Path, clock: Clock | None = None) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"schema_migrations", "db_meta", "videos"} <= tables:
            return {"schema_version": 0, "state": "not migrated"}
        version = int(conn.execute("SELECT max(version) FROM schema_migrations").fetchone()[0])
        meta = conn.execute("SELECT value FROM db_meta WHERE key = 'dataset'").fetchone()
        dataset = meta[0] if meta else "synthetic"
        db = Database(conn, dataset, clock or SystemClock(), MigrationResult((), version))
        counts: dict[str, Any] = {
            "schema_version": version,
            "state": "ready",
            "dataset": dataset,
            **SourceRepository(db).health(),
        }
        for table in ("editor_notes", "briefs", "plans", "discovery_runs"):
            counts[table] = int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608
        on = conn.execute("SELECT count(*) FROM policy_capabilities WHERE status = 'on'")
        counts["capabilities_on"] = int(on.fetchone()[0])
        return counts
    except sqlite3.Error:
        return {"schema_version": 0, "state": "unreadable"}
    finally:
        conn.close()
