"""Small live smoke check: one search.list page (5-15 IDs) + one videos.list batch.

It prints only counts, methods and units. No IDs, titles, URLs, bodies or the key are
printed, and nothing is written to any database.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .client import YouTubeClient
from .errors import StopError, YouTubeError
from .quota import QuotaLedger, estimate_hydration, estimate_search

SMOKE_MIN, SMOKE_MAX = 5, 15
DEFAULT_SMOKE_QUERY = "GTA V story mode"


def smoke_plan(max_videos: int) -> dict[str, Any]:
    _check_size(max_videos)
    est = estimate_search(1) + estimate_hydration(max_videos)
    return {"max_videos": max_videos, "estimate": est.as_dict()}


def _check_size(max_videos: int) -> None:
    if not SMOKE_MIN <= max_videos <= SMOKE_MAX:
        raise ValueError(f"smoke size must be {SMOKE_MIN}..{SMOKE_MAX} videos")


def run_smoke(client: YouTubeClient, max_videos: int, query: str) -> dict[str, Any]:
    _check_size(max_videos)
    report: dict[str, Any] = {"query_chars": len(query), "max_videos": max_videos}
    search = client.search_video_ids(query, per_page=max_videos, max_pages=1)
    report["search"] = {
        "pages": search.pages,
        "ids_returned": len(search.video_ids),
        "stop_kind": search.stop_kind,
    }
    ids = search.video_ids[:max_videos]
    if ids:
        hyd = client.hydrate(ids)
        records = hyd.records
        missing = Counter(
            m for _, p in hyd.batches for h in p.hints.values() for m in h.missing_stats
        )
        report["videos"] = {
            "requested": len(ids),
            "returned": len(records),
            "not_returned": len(hyd.not_returned),
            "stop_kind": hyd.stop_kind,
            "with_statistics": sum(r.statistics is not None for r in records),
            "views_unavailable": missing["viewCount"],
            "likes_unavailable": missing["likeCount"],
            "comments_unavailable": missing["commentCount"],
            "with_duration": sum(r.duration_iso is not None for r in records),
            "with_thumbnail": sum(r.thumbnail_url is not None for r in records),
            "embeddable_true": sum(r.embeddable is True for r in records),
            "embeddable_false": sum(r.embeddable is False for r in records),
            "with_default_language": sum(r.default_language is not None for r in records),
            "field_anomalies": sum(p.field_anomalies for _, p in hyd.batches),
            "shorts_flag": "not inferred (no reliable public flag)",
        }
    report["quota"] = client.ledger.snapshot()
    report["retries"] = client.retries
    return report


def run_smoke_safely(
    api_key: str, max_videos: int, query: str, search_budget: int = 2, units_budget: int = 4
) -> tuple[int, dict]:
    """CLI wrapper. Exit codes: 0 ok, 4 clean stop (bad key/permission/quota), 5 other."""
    ledger = QuotaLedger(search_budget=search_budget, units_budget=units_budget)
    try:
        client = YouTubeClient(api_key, ledger)
        report = run_smoke(client, max_videos, query)
    except StopError as exc:
        return 4, {
            "stopped": exc.kind,
            "status": exc.status,
            "reason": exc.reason,
            "resumable": exc.resumable,
            "quota": ledger.snapshot(),
        }
    except YouTubeError as exc:
        return 5, {
            "error": type(exc).__name__,
            "status": exc.status,
            "reason": exc.reason,
            "quota": ledger.snapshot(),
        }
    stops = [report["search"]["stop_kind"], report.get("videos", {}).get("stop_kind")]
    return (4 if any(stops) else 0), report
