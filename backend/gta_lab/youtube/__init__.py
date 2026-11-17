"""Read-only adapter for the official YouTube Data API v3 (Phase 03).

Only ``search.list``, ``videos.list``, ``channels.list`` and ``playlistItems.list`` exist
here. The adapter returns typed records for ``SourceRepository``; it never stores raw
bodies, never fetches arbitrary URLs and never logs the key.
"""

from .client import Hydration, PagedIds, RetryPolicy, YouTubeClient
from .errors import (
    BadKeyError,
    BadRequestError,
    BudgetExhaustedError,
    InvalidSeedError,
    MalformedResponseError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExhaustedError,
    StopError,
    TransientError,
    YouTubeError,
    redact,
)
from .ids import Seed, normalize_seed, normalize_seeds
from .quota import QuotaEstimate, QuotaLedger, estimate, estimate_hydration, estimate_search

__all__ = [
    "BadKeyError",
    "BadRequestError",
    "BudgetExhaustedError",
    "Hydration",
    "InvalidSeedError",
    "MalformedResponseError",
    "NotFoundError",
    "PagedIds",
    "PermissionDeniedError",
    "QuotaEstimate",
    "QuotaExhaustedError",
    "QuotaLedger",
    "RetryPolicy",
    "Seed",
    "StopError",
    "TransientError",
    "YouTubeClient",
    "YouTubeError",
    "estimate",
    "estimate_hydration",
    "estimate_search",
    "normalize_seed",
    "normalize_seeds",
    "redact",
]
