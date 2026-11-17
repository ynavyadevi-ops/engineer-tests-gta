"""Injectable UTC clock and the single timestamp format used in the database.

Every lifecycle decision (refresh due, expired, purge) takes its time from a ``Clock`` so
tests can drive retention with a ``FakeClock`` instead of waiting 30 days.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

DB_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)


class FakeClock:
    """Deterministic clock for tests and dry runs."""

    def __init__(self, start: datetime) -> None:
        self._now = _require_aware(start).astimezone(UTC).replace(microsecond=0)

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> datetime:
        self._now = self._now + timedelta(**delta)
        return self._now

    def set(self, value: datetime) -> None:
        self._now = _require_aware(value).astimezone(UTC).replace(microsecond=0)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetimes are not allowed; pass a timezone-aware value")
    return value


def to_db_ts(value: datetime) -> str:
    """Timezone-aware datetime -> fixed-width UTC text (sorts chronologically)."""
    return _require_aware(value).astimezone(UTC).strftime(DB_TS_FORMAT)


def from_db_ts(value: str) -> datetime:
    return datetime.strptime(value, DB_TS_FORMAT).replace(tzinfo=UTC)
