"""Coordination, Concurrency Locking, and Event Protocols for AGGRIX Analytics.

This module provides the shared synchronization primitives, event filtering constants,
and causal ordering specifications required for coordinating historical backfills and
the incremental aggregation worker fleet.

Key Architectural Guarantees:
1. Mutual Exclusion via PostgreSQL Advisory Locks:
   Prevents concurrent execution of the historical backfill engine and the live incremental
   event worker, avoiding lost updates, race conditions, and SQLSTATE 40001 serialization errors.
2. Transaction-Scoped Lock Lifecycle:
   Uses `pg_advisory_xact_lock` which binds lock ownership to the active database transaction.
   The lock is unconditionally released by PostgreSQL upon COMMIT or ROLLBACK, completely
   preventing lock leaks or orphaned lock states upon process termination.
3. Explicit Event Whitelisting:
   Only supported order lifecycle event types (`SUPPORTED_ORDER_EVENT_TYPES`) are selected
   and acknowledged. Unsupported domain events are excluded at the query boundary to prevent
   infinite polling loops.
4. Causal Ordering Protocol:
   Documents the causal ordering model and state transition defensiveness required when
   consuming outbox events where commit order and UUID values do not provide total ordering.
"""
from __future__ import annotations

import logging
from typing import Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

# Unique 64-bit integer identifier for the AGGRIX Analytics Aggregation lock.
# Shared across both HistoricalBackfillService and the incremental event worker.
AGGRIX_ANALYTICS_LOCK_ID: int = 849204918239102

# Supported order lifecycle events consumed by the aggregation engine.
SUPPORTED_ORDER_EVENT_TYPES: Tuple[str, ...] = (
    "order.created",
    "order.paid",
    "order.fulfilled",
    "order.cancelled",
)


class AnalyticsLockConflictError(Exception):
    """Raised when an analytics aggregation lock cannot be acquired due to active concurrency."""

    pass


def acquire_advisory_lock(conn: Connection, wait: bool = True) -> bool:
    """Acquire the PostgreSQL transaction-scoped advisory lock for analytics aggregation.

    Lock Ownership and Release Semantics:
    - In PostgreSQL, `pg_advisory_xact_lock` and `pg_try_advisory_xact_lock` allocate a
      transaction-level advisory lock tied strictly to the current database transaction.
    - There is NO explicit unlock statement required: PostgreSQL automatically releases
      the lock at the conclusion of the transaction (COMMIT or ROLLBACK).
    - If the backend worker crashes, the Python process is killed, or the TCP socket drops,
      PostgreSQL's server-side transaction abort automatically releases the lock immediately.
    - Dialect safety: On non-PostgreSQL dialects (such as in-memory SQLite during unit tests),
      this function acts as a safe no-op.

    Args:
        conn: Active SQLAlchemy database connection within an open transaction.
        wait: If True, waits for any conflicting lock holder to finish.
              If False, attempts to acquire the lock non-blockingly and raises
              AnalyticsLockConflictError if unavailable.

    Returns:
        True if the lock was acquired successfully.

    Raises:
        AnalyticsLockConflictError: If wait is False and another process holds the lock.
    """
    if conn.dialect.name != "postgresql":
        logger.debug("Non-PostgreSQL dialect (%s): skipping pg_advisory_xact_lock", conn.dialect.name)
        return True

    if wait:
        logger.debug("Acquiring blocking PostgreSQL advisory transaction lock (ID: %d)...", AGGRIX_ANALYTICS_LOCK_ID)
        conn.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": AGGRIX_ANALYTICS_LOCK_ID},
        )
        return True

    logger.info("Attempting non-blocking PostgreSQL advisory transaction lock (ID: %d)...", AGGRIX_ANALYTICS_LOCK_ID)
    acquired = conn.execute(
        text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
        {"lock_id": AGGRIX_ANALYTICS_LOCK_ID},
    ).scalar()

    if not acquired:
        error_msg = (
            f"Cannot acquire AGGRIX analytics aggregation lock (ID: {AGGRIX_ANALYTICS_LOCK_ID}). "
            "Another backfill or incremental aggregation worker process is currently active."
        )
        logger.warning(error_msg)
        raise AnalyticsLockConflictError(error_msg)

    return True


"""
================================================================================
EVENT ORDERING & CAUSAL INTEGRITY PROTOCOL SPECIFICATION
================================================================================

1. LIMITATIONS OF UUIDv4 AND created_at:
   - UUIDv4 (Random UUIDs): UUID values are randomly generated (uuid.uuid4()) and
     have zero monotonic correlation with creation time, statement order, or commit order.
     Sorting by `id ASC` provides deterministic tie-breaking across workers, but does NOT
     guarantee chronological order.
   - Transaction Timestamps: In PostgreSQL, `created_at` defaults to `now()` (or
     `transaction_timestamp()`), which returns the start time of the transaction, NOT the
     commit time.
   - Commit Race Conditions: If Transaction A begins at T0 and commits at T2 (emitting Event 1),
     while Transaction B begins at T1 and commits at T1.5 (emitting Event 2), Event 2 commits
     BEFORE Event 1, even though Event 1 has an earlier `created_at` timestamp.

2. REQUIRED CAUSAL ORDERING RULES FOR AGGREGATION:
   - Within each order, events follow a strict state lifecycle:
       order.created (null -> pending)
       order.paid (pending -> paid)
       order.fulfilled (paid -> fulfilled)
       order.cancelled (pending -> cancelled OR paid -> cancelled)
   - Polling Query Ordering:
       ORDER BY oe.created_at ASC, oe.id ASC
   - State-Defensive Handlers:
     Handlers must never assume that an event arrives with an intact predecessor in the same batch.
     If an `order.paid` arrives before `order.created` is committed, the handler must evaluate
     the current database order record or inspect `previous_status` from `event.payload` to
     apply the delta correctly without violating non-negative constraints.

3. CONSUMER RECEIPT SCHEMA (order_id NULLABILITY):
   - In `analytics_consumer_events`, `order_id` is defined as `nullable=False`.
   - Rationale: The `analytics_worker` consumer exclusively processes order lifecycle events.
     Every supported event (`order.*`) has a mandatory `order_id`. Retaining non-nullability
     strictly enforces relational integrity and prevents phantom receipts from entering the
     analytics deduplication tracking table.
================================================================================
"""
