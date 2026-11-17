"""Versioned plain-SQL migrations (``migrations/NNNN_name.sql``).

* Each pending file runs in its own transaction together with its ``schema_migrations``
  row, so a failure leaves no partial schema and no version record.
* Re-running is a no-op. An applied file whose checksum changed, or a database that knows
  a version this code does not ship, stops with ``MigrationError`` instead of guessing.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..clock import Clock, SystemClock, to_db_ts

MIGRATION_FILE_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


@dataclass(frozen=True)
class MigrationResult:
    applied: tuple[int, ...]
    current_version: int


def default_migrations_dir() -> Path:
    # backend/gta_lab/db/migrate.py -> repo root
    return Path(__file__).resolve().parents[3] / "migrations"


def discover(migrations_dir: Path | None = None) -> list[Migration]:
    directory = migrations_dir or default_migrations_dir()
    if not directory.is_dir():
        raise MigrationError(f"migrations folder not found: {directory}")
    found: list[Migration] = []
    for path in sorted(directory.iterdir()):
        if path.suffix != ".sql":
            continue
        match = MIGRATION_FILE_RE.match(path.name)
        if not match:
            raise MigrationError(f"unexpected migration file name: {path.name}")
        raw = path.read_bytes()
        found.append(
            Migration(
                version=int(match.group(1)),
                name=match.group(2),
                # Normalise line endings so a Git autocrlf checkout keeps the same checksum.
                sql=raw.decode("utf-8").replace("\r\n", "\n"),
                checksum=hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
            )
        )
    versions = [m.version for m in found]
    if versions != list(range(1, len(found) + 1)):
        raise MigrationError(f"migration versions must be contiguous from 0001: {versions}")
    return found


def _ensure_tracking_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version        INTEGER PRIMARY KEY,
            name           TEXT NOT NULL,
            checksum       TEXT NOT NULL,
            applied_at_utc TEXT NOT NULL
        ) STRICT
        """
    )


def applied_versions(conn: sqlite3.Connection) -> dict[int, str]:
    _ensure_tracking_table(conn)
    rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
    return {int(v): str(c) for v, c in rows}


def migrate(
    conn: sqlite3.Connection,
    migrations_dir: Path | None = None,
    clock: Clock | None = None,
) -> MigrationResult:
    """Apply pending migrations. ``conn`` must be in autocommit mode (isolation_level=None)."""
    if conn.isolation_level is not None:
        raise MigrationError("migrate() needs an autocommit connection (isolation_level=None)")
    clock = clock or SystemClock()
    migrations = discover(migrations_dir)
    known = {m.version: m for m in migrations}
    applied = applied_versions(conn)

    unknown = sorted(set(applied) - set(known))
    if unknown:
        raise MigrationError(f"database has migrations this code does not know: {unknown}")
    for version, checksum in applied.items():
        if known[version].checksum != checksum:
            raise MigrationError(
                f"migration {version:04d}_{known[version].name} changed after it was applied"
            )

    newly_applied: list[int] = []
    for m in migrations:
        if m.version in applied:
            continue
        # Values are validated digits, [a-z0-9_], hex and a fixed timestamp: no injection
        # surface. They are inlined because the record must share the script's transaction.
        record = (
            "INSERT INTO schema_migrations (version, name, checksum, applied_at_utc) "  # noqa: S608
            f"VALUES ({m.version}, '{m.name}', '{m.checksum}', '{to_db_ts(clock.now())}');"
        )
        try:
            conn.executescript(f"BEGIN IMMEDIATE;\n{m.sql}\n;\n{record}\nCOMMIT;")
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise MigrationError(f"migration {m.version:04d}_{m.name} failed: {exc}") from exc
        newly_applied.append(m.version)

    current = max(known) if known else 0
    return MigrationResult(applied=tuple(newly_applied), current_version=current)
