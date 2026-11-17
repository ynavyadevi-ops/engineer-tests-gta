"""Per-bucket quota estimation and accounting.

Costs and default limits come from the official quota page (verified 2026-11-17, see
``docs/YOUTUBE_POLICY.md``): ``search.list`` has its own bucket (default 100 calls/day,
1 unit per call); ``videos.list``, ``channels.list`` and ``playlistItems.list`` cost 1
unit each from the shared default 10,000 units/day. The real project limits are whatever
the Cloud Console shows, so both limits are settings, not constants, and a local budget
is a self-imposed cap, never permission to exceed the Console values.

Google charges at least one unit for every request, including invalid ones, so every
attempt (retries included) is charged here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .errors import BudgetExhaustedError

Method = Literal["search.list", "videos.list", "channels.list", "playlistItems.list"]
Bucket = Literal["search", "units"]

# method -> (bucket, cost per request in that bucket)
METHOD_COST: dict[Method, tuple[Bucket, int]] = {
    "search.list": ("search", 1),
    "videos.list": ("units", 1),
    "channels.list": ("units", 1),
    "playlistItems.list": ("units", 1),
}

DEFAULT_SEARCH_CALLS_PER_DAY = 100
DEFAULT_UNITS_PER_DAY = 10_000
MAX_IDS_PER_REQUEST = 50
MAX_RESULTS_PER_PAGE = 50


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


@dataclass(frozen=True)
class QuotaEstimate:
    search: int = 0
    units: int = 0
    requests: dict[str, int] = field(default_factory=dict)

    def __add__(self, other: QuotaEstimate) -> QuotaEstimate:
        merged = dict(self.requests)
        for k, v in other.requests.items():
            merged[k] = merged.get(k, 0) + v
        return QuotaEstimate(self.search + other.search, self.units + other.units, merged)

    def as_dict(self) -> dict[str, object]:
        return {
            "search_bucket": self.search,
            "units_bucket": self.units,
            "requests": dict(sorted(self.requests.items())),
        }


def estimate(method: Method, requests: int) -> QuotaEstimate:
    if requests < 0:
        raise ValueError("requests must be >= 0")
    bucket, cost = METHOD_COST[method]
    amount = cost * requests
    return QuotaEstimate(
        search=amount if bucket == "search" else 0,
        units=amount if bucket == "units" else 0,
        requests={method: requests} if requests else {},
    )


def estimate_hydration(video_count: int) -> QuotaEstimate:
    """videos.list cost to hydrate ``video_count`` IDs in batches of 50 (no retries)."""
    return estimate("videos.list", ceil_div(max(video_count, 0), MAX_IDS_PER_REQUEST))


def estimate_search(pages: int) -> QuotaEstimate:
    return estimate("search.list", pages)


def estimate_uploads(channel_count: int, pages_per_channel: int) -> QuotaEstimate:
    """channels.list lookups (50 per call) plus playlistItems pages per channel."""
    return estimate("channels.list", ceil_div(channel_count, MAX_IDS_PER_REQUEST)) + estimate(
        "playlistItems.list", channel_count * pages_per_channel
    )


class QuotaLedger:
    """Local budget per bucket. ``charge`` refuses before a request would exceed it."""

    def __init__(self, search_budget: int, units_budget: int) -> None:
        if search_budget < 0 or units_budget < 0:
            raise ValueError("budgets must be >= 0")
        self.budget: dict[Bucket, int] = {"search": search_budget, "units": units_budget}
        self.used: dict[Bucket, int] = {"search": 0, "units": 0}
        self.requests: dict[str, int] = {}

    def remaining(self, bucket: Bucket) -> int:
        return self.budget[bucket] - self.used[bucket]

    def can_afford(self, est: QuotaEstimate) -> bool:
        return est.search <= self.remaining("search") and est.units <= self.remaining("units")

    def charge(self, method: Method) -> None:
        bucket, cost = METHOD_COST[method]
        if self.used[bucket] + cost > self.budget[bucket]:
            raise BudgetExhaustedError(
                f"local {bucket} budget exhausted ({self.used[bucket]}/{self.budget[bucket]})",
                reason=f"budget_{bucket}",
            )
        self.used[bucket] += cost
        self.requests[method] = self.requests.get(method, 0) + 1

    def snapshot(self) -> dict[str, object]:
        return {
            "used": dict(self.used),
            "budget": dict(self.budget),
            "requests": dict(sorted(self.requests.items())),
        }
