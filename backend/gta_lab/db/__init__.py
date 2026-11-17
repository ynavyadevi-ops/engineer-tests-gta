"""Local SQLite persistence: migrations, repositories and the retention lifecycle.

The repository classes are the persistence interface. A hosted (Postgres) adapter added in
Phase 14 must provide the same methods and the same retention guarantees.
"""

from .connection import (
    Database,
    DatasetMismatchError,
    UnsafeLocationError,
    dataset_for,
    open_database,
    open_for_settings,
)
from .editorial import BriefDraft, CopiedApiDataError, EditorialRepository, IneligibleSourceError
from .migrate import MigrationError, migrate
from .planning import LedgerRepository, OwnerMetrics, PlanRepository
from .retention import PurgeReport, RetentionPolicy, purge_expired
from .runs import Hit, RunRepository
from .sources import (
    ChannelRecord,
    InvalidSourceIdError,
    SourceRepository,
    VideoRecord,
    VideoStatistics,
)

__all__ = [
    "BriefDraft",
    "ChannelRecord",
    "CopiedApiDataError",
    "Database",
    "DatasetMismatchError",
    "EditorialRepository",
    "Hit",
    "IneligibleSourceError",
    "InvalidSourceIdError",
    "LedgerRepository",
    "MigrationError",
    "OwnerMetrics",
    "PlanRepository",
    "PurgeReport",
    "RetentionPolicy",
    "RunRepository",
    "SourceRepository",
    "UnsafeLocationError",
    "VideoRecord",
    "VideoStatistics",
    "dataset_for",
    "migrate",
    "open_database",
    "open_for_settings",
    "purge_expired",
]
