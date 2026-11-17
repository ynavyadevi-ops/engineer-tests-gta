"""Shared helpers for database tests. All IDs and numbers here are synthetic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gta_lab.clock import FakeClock
from gta_lab.db import Database, VideoRecord, VideoStatistics, open_database

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def fx(n: int) -> str:
    """Synthetic video ID. Contains ':' so it can never be a real YouTube ID."""
    return f"fixture:vid-{n:03d}"


def rec(
    n: int,
    title: str | None = None,
    views: int | None = 100,
    likes: int | None = 10,
    comments: int | None = 1,
    thumb: str | None = None,
    stats: bool = True,
) -> VideoRecord:
    return VideoRecord(
        video_id=fx(n),
        channel_id="fixture:chan-001",
        channel_title="Synthetic Channel One",
        title=title or f"Synthetic test video number {n}",
        published_at=datetime(2020, 5, 1, tzinfo=UTC),
        duration_iso="PT8M",
        thumbnail_url=thumb or f"https://example.invalid/thumb/{n}.jpg",
        embeddable=True,
        statistics=VideoStatistics(views, likes, comments) if stats else None,
    )


def open_synthetic(tmp_path: Path, clock: FakeClock | None = None) -> Database:
    return open_database(tmp_path / "db dir" / "demo.sqlite3", "synthetic", clock or FakeClock(T0))
