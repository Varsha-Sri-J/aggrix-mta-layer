"""AGGRIX Analytics & Aggregation Layer package."""

from app.analytics.backfill import BackfillResult, HistoricalBackfillService
from app.analytics.coordination import (
    AGGRIX_ANALYTICS_LOCK_ID,
    SUPPORTED_ORDER_EVENT_TYPES,
    AnalyticsLockConflictError,
    acquire_advisory_lock,
)
from app.analytics.worker import (
    IncrementalAggregationWorker,
    WorkerBatchResult,
    run_worker_daemon,
)
from app.analytics.service import (
    AnalyticsQueryService,
    InvalidDateRangeError,
    TenantNotFoundError,
)
from app.models.analytics_dead_letter_event import AnalyticsDeadLetterEvent

__all__ = [
    "HistoricalBackfillService",
    "BackfillResult",
    "IncrementalAggregationWorker",
    "WorkerBatchResult",
    "run_worker_daemon",
    "AnalyticsDeadLetterEvent",
    "AGGRIX_ANALYTICS_LOCK_ID",
    "SUPPORTED_ORDER_EVENT_TYPES",
    "AnalyticsLockConflictError",
    "acquire_advisory_lock",
    "AnalyticsQueryService",
    "TenantNotFoundError",
    "InvalidDateRangeError",
]
