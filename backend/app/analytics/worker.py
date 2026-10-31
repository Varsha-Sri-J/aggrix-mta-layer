"""Incremental Aggregation Worker for AGGRIX Analytics Engine.

Provides reliable, idempotent, event-driven streaming aggregation from transactional
`outbox_events` into:
1. `daily_tenant_metrics`
2. `daily_product_metrics`
3. `analytics_consumer_events` (successful receipts)
4. `analytics_dead_letter_events` (quarantined failures and retries)

Core Architectural Guarantees:
- Event Whitelisting: Processes only supported order lifecycle events (`SUPPORTED_ORDER_EVENT_TYPES`).
- At-Least-Once & Idempotent Processing: Uses `analytics_consumer_events` receipts to skip already processed events.
- Causal Ordering & Out-of-Order Defensiveness: Inspects prior events per order via indexed receipts,
  preventing double-counting when orders transition (e.g. pending -> paid -> fulfilled) and safely
  resolving out-of-order delivery.
- Mutual Exclusion: Coordinates with historical backfill using `AGGRIX_ANALYTICS_LOCK_ID`.
- Transactional Atomicity: Processes each batch within an atomic database transaction.
- Dead-Letter Handling & Poison-Pill Isolation: Uses per-event savepoints (`begin_nested()`) so a single
  failing event does not block valid batch events. Tracks retry attempts in `analytics_dead_letter_events`
  and quarantines permanently failing events after 3 attempts.
- Daemon Runner: Supports continuous polling, graceful SIGINT/SIGTERM shutdown, and adaptive sleep.
"""
from __future__ import annotations

import json
import logging
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.analytics.coordination import (
    AGGRIX_ANALYTICS_LOCK_ID,
    SUPPORTED_ORDER_EVENT_TYPES,
    AnalyticsLockConflictError,
    acquire_advisory_lock,
)
from app.core.config import settings
from app.database.connection import create_database_engine, engine as default_engine
from app.models.analytics_consumer_event import AnalyticsConsumerEvent
from app.models.analytics_dead_letter_event import AnalyticsDeadLetterEvent
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerBatchResult:
    """Structured report returned after executing an incremental worker batch."""

    events_polled: int
    events_processed: int
    events_skipped: int
    events_failed: int
    duration_seconds: float
    order_ids_affected: List[uuid.UUID] = field(default_factory=list)


class IncrementalAggregationWorker:
    """Incremental event consumer transforming domain outbox events into daily analytics summaries."""

    def __init__(
        self,
        consumer_name: Optional[str] = None,
        tenant_id: Optional[Union[uuid.UUID, str]] = None,
        batch_size: Optional[int] = None,
        polling_interval_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        engine: Optional[Engine] = None,
    ) -> None:
        """Initialize the incremental aggregation worker.

        Args:
            consumer_name: Unique identifier for tracking event processing receipts.
            tenant_id: Optional UUID to restrict worker processing to a specific tenant.
            batch_size: Maximum number of outbox events to poll per batch iteration.
            polling_interval_seconds: Delay between polling cycles when queue is empty.
            max_retries: Maximum attempts before quarantining an event into DLQ.
            engine: Optional SQLAlchemy Engine. Defaults to application database engine.
        """
        self.consumer_name = consumer_name or settings.ANALYTICS_WORKER_CONSUMER_NAME
        self.tenant_id = uuid.UUID(str(tenant_id)) if tenant_id is not None else None
        self.batch_size = batch_size or settings.ANALYTICS_WORKER_BATCH_SIZE
        self.polling_interval_seconds = (
            polling_interval_seconds
            if polling_interval_seconds is not None
            else settings.ANALYTICS_WORKER_POLL_INTERVAL_SECONDS
        )
        self.max_retries = (
            max_retries
            if max_retries is not None
            else settings.ANALYTICS_WORKER_MAX_RETRIES
        )
        self.engine = engine or default_engine or create_database_engine()
        self._tz_cache: Dict[uuid.UUID, ZoneInfo] = {}

    def poll_unprocessed_events(
        self,
        conn: Connection,
        batch_size: Optional[int] = None,
    ) -> List[OutboxEvent]:
        """Poll the next batch of unconsumed, supported order outbox events.

        Excludes:
        1. Any event whose `id` already exists in `analytics_consumer_events` for this consumer.
        2. Any event whose `event_type` is not in `SUPPORTED_ORDER_EVENT_TYPES`.
        3. Any event quarantined in `analytics_dead_letter_events` with attempts >= max_retries.

        Ordering:
        Ordered by `oe.created_at ASC, oe.id ASC` for causal progression.
        On PostgreSQL, uses `FOR UPDATE OF oe SKIP LOCKED` to allow safe multi-worker scaling.
        """
        limit = batch_size or self.batch_size
        dialect_name = conn.dialect.name
        tenant_filter = "AND oe.tenant_id = :tenant_id" if self.tenant_id else ""
        params: Dict[str, Any] = {
            "consumer_name": self.consumer_name,
            "limit": limit,
            "max_retries": self.max_retries,
        }
        if self.tenant_id:
            params["tenant_id"] = str(self.tenant_id)

        skip_locked_clause = "FOR UPDATE OF oe SKIP LOCKED" if dialect_name == "postgresql" else ""

        sql = f"""
        SELECT oe.id, oe.tenant_id, oe.event_type, oe.payload, oe.created_at, oe.processed_at
        FROM outbox_events oe
        WHERE oe.event_type IN ('order.created', 'order.paid', 'order.fulfilled', 'order.cancelled')
          AND NOT EXISTS (
              SELECT 1 
              FROM analytics_consumer_events ace
              WHERE ace.consumer_name = :consumer_name
                AND ace.event_id = oe.id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM analytics_dead_letter_events dle
              WHERE dle.consumer_name = :consumer_name
                AND dle.event_id = oe.id
                AND dle.attempts >= :max_retries
          )
          {tenant_filter}
        ORDER BY oe.created_at ASC, oe.id ASC
        LIMIT :limit
        {skip_locked_clause};
        """
        rows = conn.execute(text(sql), params).fetchall()
        events: List[OutboxEvent] = []
        for r in rows:
            payload_data = r[3]
            if isinstance(payload_data, str):
                try:
                    payload_data = json.loads(payload_data)
                except Exception:
                    payload_data = {}
            events.append(
                OutboxEvent(
                    id=r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])),
                    tenant_id=r[1] if isinstance(r[1], uuid.UUID) else uuid.UUID(str(r[1])),
                    event_type=r[2],
                    payload=payload_data,
                    created_at=r[4],
                    processed_at=r[5],
                )
            )
        return events

    def process_batch(
        self,
        conn: Optional[Connection] = None,
        session: Optional[Session] = None,
        batch_size: Optional[int] = None,
        propagate_errors: bool = False,
    ) -> WorkerBatchResult:
        """Process a batch of unconsumed events atomically.

        Args:
            conn: Optional active database connection.
            session: Optional active SQLAlchemy session.
            batch_size: Optional override for batch limit.
            propagate_errors: If True, re-raises event exceptions to trigger full batch rollback.

        Returns:
            WorkerBatchResult detailing batch execution metrics.
        """
        start_time = time.perf_counter()

        if session is not None:
            c = session.connection()
            nested = c.begin_nested()
            try:
                res = self._execute_batch(c, batch_size, start_time, propagate_errors=propagate_errors)
                nested.commit()
                session.expire_all()
                return res
            except Exception:
                nested.rollback()
                raise

        if conn is not None:
            return self._execute_batch(conn, batch_size, start_time, propagate_errors=propagate_errors)

        iso_level = (
            "REPEATABLE READ"
            if self.engine.dialect.name == "postgresql"
            else "SERIALIZABLE"
        )
        with self.engine.connect().execution_options(isolation_level=iso_level) as c:
            with c.begin():
                return self._execute_batch(c, batch_size, start_time, propagate_errors=propagate_errors)

    def _execute_batch(
        self,
        conn: Connection,
        batch_size: Optional[int],
        start_time: float,
        propagate_errors: bool = False,
    ) -> WorkerBatchResult:
        """Internal execution routine within an open transaction."""
        # 1. Acquire coordination advisory lock
        acquire_advisory_lock(conn, wait=True)

        events = self.poll_unprocessed_events(conn, batch_size=batch_size)
        polled_count = len(events)
        processed_count = 0
        skipped_count = 0
        failed_count = 0
        affected_orders: List[uuid.UUID] = []

        if not events:
            logger.debug("Incremental worker polled 0 unprocessed events.")
            return WorkerBatchResult(
                events_polled=0,
                events_processed=0,
                events_skipped=0,
                events_failed=0,
                duration_seconds=time.perf_counter() - start_time,
                order_ids_affected=[],
            )

        logger.info(
            "Worker [%s] processing batch of %d outbox events...",
            self.consumer_name,
            polled_count,
        )

        # Batch prefetch lookups to minimize SQL roundtrips
        batch_order_ids: List[uuid.UUID] = []
        for e in events:
            oid_s = e.payload.get("order_id") if isinstance(e.payload, dict) else None
            if oid_s:
                try:
                    batch_order_ids.append(uuid.UUID(str(oid_s)))
                except Exception:
                    pass

        batch_receipts: Dict[uuid.UUID, Set[str]] = {}
        batch_orders: Dict[Tuple[uuid.UUID, uuid.UUID], Tuple[datetime, str, Decimal]] = {}
        batch_items: Dict[Tuple[uuid.UUID, uuid.UUID], List[Tuple[uuid.UUID, int, Decimal]]] = {}

        if batch_order_ids:
            rc_rows = conn.execute(
                select(AnalyticsConsumerEvent.order_id, AnalyticsConsumerEvent.event_type).where(
                    AnalyticsConsumerEvent.consumer_name == self.consumer_name,
                    AnalyticsConsumerEvent.order_id.in_(batch_order_ids),
                )
            ).fetchall()
            for r in rc_rows:
                batch_receipts.setdefault(r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])), set()).add(r[1])

            o_rows = conn.execute(
                select(Order.tenant_id, Order.id, Order.created_at, Order.currency, Order.total_amount).where(
                    Order.id.in_(batch_order_ids)
                )
            ).fetchall()
            for r in o_rows:
                tid = r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0]))
                oid = r[1] if isinstance(r[1], uuid.UUID) else uuid.UUID(str(r[1]))
                batch_orders[(tid, oid)] = (r[2], r[3], Decimal(str(r[4])))

            it_rows = conn.execute(
                select(OrderItem.tenant_id, OrderItem.order_id, OrderItem.product_id, OrderItem.quantity, OrderItem.unit_price).where(
                    OrderItem.order_id.in_(batch_order_ids)
                )
            ).fetchall()
            for r in it_rows:
                tid = r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0]))
                oid = r[1] if isinstance(r[1], uuid.UUID) else uuid.UUID(str(r[1]))
                pid = r[2] if isinstance(r[2], uuid.UUID) else uuid.UUID(str(r[2]))
                batch_items.setdefault((tid, oid), []).append((pid, int(r[3]), Decimal(str(r[4]))))

        for event in events:
            sp = conn.begin_nested()
            try:
                was_processed = self._process_single_event(
                    conn,
                    event,
                    prefetch_receipts=batch_receipts,
                    prefetch_orders=batch_orders,
                    prefetch_items=batch_items,
                )
                if was_processed:
                    processed_count += 1
                    # Clear transient failure record on success
                    self._cleanup_dead_letter_on_success(conn, event.id)
                    oid: Optional[uuid.UUID] = None
                    try:
                        oid = uuid.UUID(str(event.payload.get("order_id")))
                        affected_orders.append(oid)
                    except Exception:
                        pass
                    try:
                        self._broadcast_event(conn, event, oid)
                    except Exception as b_err:
                        logger.debug("Broadcast event notification warning: %s", b_err)
                else:
                    skipped_count += 1
                sp.commit()
            except Exception as exc:
                sp.rollback()
                failed_count += 1
                logger.error(
                    "Worker [%s] failed to process event ID %s (type: %s): %s",
                    self.consumer_name,
                    event.id,
                    event.event_type,
                    str(exc),
                )
                self._record_event_failure(conn, event, exc)
                if propagate_errors:
                    raise

        duration = time.perf_counter() - start_time
        logger.info(
            "Worker [%s] batch complete: %d polled, %d processed, %d skipped, %d failed in %.3fs",
            self.consumer_name,
            polled_count,
            processed_count,
            skipped_count,
            failed_count,
            duration,
        )

        return WorkerBatchResult(
            events_polled=polled_count,
            events_processed=processed_count,
            events_skipped=skipped_count,
            events_failed=failed_count,
            duration_seconds=duration,
            order_ids_affected=affected_orders,
        )

    def _process_single_event(
        self,
        conn: Connection,
        event: OutboxEvent,
        prefetch_receipts: Optional[Dict[uuid.UUID, Set[str]]] = None,
        prefetch_orders: Optional[Dict[Tuple[uuid.UUID, uuid.UUID], Tuple[datetime, str, Decimal]]] = None,
        prefetch_items: Optional[Dict[Tuple[uuid.UUID, uuid.UUID], List[Tuple[uuid.UUID, int, Decimal]]]] = None,
    ) -> bool:
        """Process an individual event with full causal and out-of-order defensiveness.

        Returns True if the event was processed and receipt written, False if skipped.
        Raises ValueError if event payload is fundamentally malformed (no order_id).
        """
        payload = event.payload if isinstance(event.payload, dict) else {}
        order_id_str = payload.get("order_id")
        if not order_id_str:
            raise ValueError(f"Event {event.id} missing required order_id in payload")

        try:
            order_id = uuid.UUID(str(order_id_str))
        except Exception as err:
            raise ValueError(f"Event {event.id} has invalid order_id '{order_id_str}': {err}") from err

        tenant_id = event.tenant_id
        event_type = event.event_type

        # 1. Inspect existing receipts for this order by this consumer
        if prefetch_receipts is not None:
            prior_event_types = prefetch_receipts.setdefault(order_id, set())
        else:
            receipt_query = select(AnalyticsConsumerEvent.event_type).where(
                AnalyticsConsumerEvent.consumer_name == self.consumer_name,
                AnalyticsConsumerEvent.order_id == order_id,
            )
            prior_event_types = set(conn.execute(receipt_query).scalars().all())

        if event_type in prior_event_types:
            logger.debug("Event type %s for order %s already recorded, skipping.", event_type, order_id)
            return False

        # 2. Retrieve order entity for canonical placement timestamp and currency
        if prefetch_orders is not None:
            cached_order = prefetch_orders.get((tenant_id, order_id))
            if cached_order is not None:
                order_created_at, currency, total_amount = cached_order
            else:
                raw_time = payload.get("occurred_at")
                order_created_at = (
                    datetime.fromisoformat(raw_time)
                    if raw_time
                    else event.created_at
                )
                currency = payload.get("currency", "USD")
                total_amount = Decimal(str(payload.get("total_amount", "0.00")))
        else:
            order_row = conn.execute(
                select(Order.created_at, Order.currency, Order.total_amount).where(
                    Order.tenant_id == tenant_id,
                    Order.id == order_id,
                )
            ).fetchone()

            if order_row:
                order_created_at, currency, total_amount = order_row[0], order_row[1], Decimal(str(order_row[2]))
            else:
                # Fallback to payload metadata if order was mock-created or detached
                raw_time = payload.get("occurred_at")
                order_created_at = (
                    datetime.fromisoformat(raw_time)
                    if raw_time
                    else event.created_at
                )
                currency = payload.get("currency", "USD")
                total_amount = Decimal(str(payload.get("total_amount", "0.00")))

        # 3. Retrieve tenant reporting timezone to determine local cohort metric_date
        tz = self._tz_cache.get(tenant_id)
        if tz is None:
            tz_str = conn.execute(
                select(Tenant.timezone).where(Tenant.id == tenant_id)
            ).scalar() or "UTC"
            try:
                tz = ZoneInfo(tz_str)
            except Exception:
                tz = ZoneInfo("UTC")
            self._tz_cache[tenant_id] = tz

        dt = order_created_at if order_created_at.tzinfo else order_created_at.replace(tzinfo=timezone.utc)
        metric_date = dt.astimezone(tz).date()

        # 4. Retrieve order line items for product-level rollup
        if prefetch_items is not None:
            order_items = prefetch_items.get((tenant_id, order_id), [])
        else:
            item_rows = conn.execute(
                select(OrderItem.product_id, OrderItem.quantity, OrderItem.unit_price).where(
                    OrderItem.tenant_id == tenant_id,
                    OrderItem.order_id == order_id,
                )
            ).fetchall()
            order_items = [(r[0], int(r[1]), Decimal(str(r[2]))) for r in item_rows]

        # 5. Compute tenant and product metric deltas based on state lifecycle
        t_delta, p_deltas = self._calculate_transition_deltas(
            event_type=event_type,
            total_amount=total_amount,
            order_items=order_items,
            prior_events=prior_event_types,
            previous_status=payload.get("previous_status"),
        )

        # 6. Apply summary metric deltas via upsert
        self._apply_tenant_metric_delta(conn, tenant_id, metric_date, currency, t_delta)
        for prod_id, p_delta in p_deltas.items():
            self._apply_product_metric_delta(conn, tenant_id, prod_id, metric_date, currency, p_delta)

        # 7. Write consumer receipt atomically
        self._write_consumer_receipt(conn, event.id, tenant_id, event_type, order_id)
        if prefetch_receipts is not None:
            prior_event_types.add(event_type)

        return True

    def _calculate_transition_deltas(
        self,
        event_type: str,
        total_amount: Decimal,
        order_items: List[Tuple[uuid.UUID, int, Decimal]],
        prior_events: Set[str],
        previous_status: Optional[str],
    ) -> Tuple[Dict[str, Any], Dict[uuid.UUID, Dict[str, Any]]]:
        """Calculate state transition deltas with strict causal defensiveness.

        Guarantees:
        - Out-of-order handling: If order.paid arrives before order.created, order is registered
          directly as paid (net_sales += total, orders_count += 1, pending = 0).
        - No double-counting: When order.created arrives after order.paid, creation deltas are skipped.
        - Refund handling: If order.cancelled has previous_status='paid', net_sales is decremented.
        - Multi-item accumulation: Correctly sums quantities and amounts for multiple lines of same product.
        - Product orders_count: Incremented once per unique product in the order.
        """
        # Tenant deltas
        t_delta: Dict[str, Any] = {
            "orders_count": 0,
            "gross_sales": Decimal("0.00"),
            "net_sales": Decimal("0.00"),
            "pending_orders_count": 0,
            "pending_sales": Decimal("0.00"),
            "cancelled_orders_count": 0,
            "cancelled_sales": Decimal("0.00"),
        }

        # Product deltas: pre-initialize uniquely per product
        p_deltas: Dict[uuid.UUID, Dict[str, Any]] = {}
        for pid, _, _ in order_items:
            if pid not in p_deltas:
                p_deltas[pid] = {
                    "units_sold_gross": 0,
                    "units_sold_net": 0,
                    "gross_sales": Decimal("0.00"),
                    "net_sales": Decimal("0.00"),
                    "pending_units": 0,
                    "pending_sales": Decimal("0.00"),
                    "cancelled_units": 0,
                    "cancelled_sales": Decimal("0.00"),
                    "orders_count": 0,
                }

        created_seen = "order.created" in prior_events
        paid_seen = "order.paid" in prior_events
        cancelled_seen = "order.cancelled" in prior_events

        if event_type == "order.created":
            if paid_seen or cancelled_seen:
                # Order was already initialized by an out-of-order terminal event; skip duplicate creation
                logger.info("order.created arrived after order was already recognized; delta suppressed.")
            else:
                # Normal creation: initial pending state
                t_delta["orders_count"] = 1
                t_delta["gross_sales"] = total_amount
                t_delta["pending_orders_count"] = 1
                t_delta["pending_sales"] = total_amount

                seen_pids: Set[uuid.UUID] = set()
                for pid, qty, price in order_items:
                    amt = Decimal(str(qty)) * price
                    p_deltas[pid]["units_sold_gross"] += qty
                    p_deltas[pid]["gross_sales"] += amt
                    p_deltas[pid]["pending_units"] += qty
                    p_deltas[pid]["pending_sales"] += amt
                    if pid not in seen_pids:
                        p_deltas[pid]["orders_count"] += 1
                        seen_pids.add(pid)

        elif event_type == "order.paid":
            if not created_seen:
                # Out-of-order: order.paid arrived before order.created
                # Initialize order directly in recognized paid state
                logger.info("order.paid arrived before order.created; initializing directly as recognized.")
                t_delta["orders_count"] = 1
                t_delta["gross_sales"] = total_amount
                t_delta["net_sales"] = total_amount

                seen_pids: Set[uuid.UUID] = set()
                for pid, qty, price in order_items:
                    amt = Decimal(str(qty)) * price
                    p_deltas[pid]["units_sold_gross"] += qty
                    p_deltas[pid]["gross_sales"] += amt
                    p_deltas[pid]["units_sold_net"] += qty
                    p_deltas[pid]["net_sales"] += amt
                    if pid not in seen_pids:
                        p_deltas[pid]["orders_count"] += 1
                        seen_pids.add(pid)
            else:
                # Normal transition: pending -> paid
                t_delta["pending_orders_count"] = -1
                t_delta["pending_sales"] = -total_amount
                t_delta["net_sales"] = total_amount

                for pid, qty, price in order_items:
                    amt = Decimal(str(qty)) * price
                    p_deltas[pid]["pending_units"] -= qty
                    p_deltas[pid]["pending_sales"] -= amt
                    p_deltas[pid]["units_sold_net"] += qty
                    p_deltas[pid]["net_sales"] += amt

        elif event_type == "order.fulfilled":
            if not created_seen and not paid_seen:
                # Arrived ahead of all previous events
                t_delta["orders_count"] = 1
                t_delta["gross_sales"] = total_amount
                t_delta["net_sales"] = total_amount

                seen_pids: Set[uuid.UUID] = set()
                for pid, qty, price in order_items:
                    amt = Decimal(str(qty)) * price
                    p_deltas[pid]["units_sold_gross"] += qty
                    p_deltas[pid]["gross_sales"] += amt
                    p_deltas[pid]["units_sold_net"] += qty
                    p_deltas[pid]["net_sales"] += amt
                    if pid not in seen_pids:
                        p_deltas[pid]["orders_count"] += 1
                        seen_pids.add(pid)
            else:
                # Realized revenue was already recognized at order.paid; 0 financial delta
                pass

        elif event_type == "order.cancelled":
            if not created_seen and not paid_seen:
                # Arrived ahead of creation: initialize directly as cancelled
                t_delta["orders_count"] = 1
                t_delta["gross_sales"] = total_amount
                t_delta["cancelled_orders_count"] = 1
                t_delta["cancelled_sales"] = total_amount

                seen_pids: Set[uuid.UUID] = set()
                for pid, qty, price in order_items:
                    amt = Decimal(str(qty)) * price
                    p_deltas[pid]["units_sold_gross"] += qty
                    p_deltas[pid]["gross_sales"] += amt
                    p_deltas[pid]["cancelled_units"] += qty
                    p_deltas[pid]["cancelled_sales"] += amt
                    if pid not in seen_pids:
                        p_deltas[pid]["orders_count"] += 1
                        seen_pids.add(pid)
            elif previous_status == "paid" or paid_seen:
                # Cancellation of a paid order (Refund)
                t_delta["net_sales"] = -total_amount
                t_delta["cancelled_orders_count"] = 1
                t_delta["cancelled_sales"] = total_amount

                for pid, qty, price in order_items:
                    amt = Decimal(str(qty)) * price
                    p_deltas[pid]["units_sold_net"] -= qty
                    p_deltas[pid]["net_sales"] -= amt
                    p_deltas[pid]["cancelled_units"] += qty
                    p_deltas[pid]["cancelled_sales"] += amt
            else:
                # Cancellation of a pending order
                t_delta["pending_orders_count"] = -1
                t_delta["pending_sales"] = -total_amount
                t_delta["cancelled_orders_count"] = 1
                t_delta["cancelled_sales"] = total_amount

                for pid, qty, price in order_items:
                    amt = Decimal(str(qty)) * price
                    p_deltas[pid]["pending_units"] -= qty
                    p_deltas[pid]["pending_sales"] -= amt
                    p_deltas[pid]["cancelled_units"] += qty
                    p_deltas[pid]["cancelled_sales"] += amt

        return t_delta, p_deltas

    def _apply_tenant_metric_delta(
        self,
        conn: Connection,
        tenant_id: uuid.UUID,
        metric_date: Any,
        currency: str,
        delta: Dict[str, Any],
    ) -> None:
        """Apply incremental delta to daily_tenant_metrics using UPDATE-first pattern."""
        dialect_name = conn.dialect.name
        now_dt = datetime.now(timezone.utc)

        update_stmt = (
            update(DailyTenantMetric)
            .where(
                DailyTenantMetric.tenant_id == tenant_id,
                DailyTenantMetric.metric_date == metric_date,
                DailyTenantMetric.currency == currency,
            )
            .values(
                orders_count=DailyTenantMetric.orders_count + delta["orders_count"],
                gross_sales=DailyTenantMetric.gross_sales + delta["gross_sales"],
                net_sales=DailyTenantMetric.net_sales + delta["net_sales"],
                pending_orders_count=DailyTenantMetric.pending_orders_count + delta["pending_orders_count"],
                pending_sales=DailyTenantMetric.pending_sales + delta["pending_sales"],
                cancelled_orders_count=DailyTenantMetric.cancelled_orders_count + delta["cancelled_orders_count"],
                cancelled_sales=DailyTenantMetric.cancelled_sales + delta["cancelled_sales"],
                updated_at=now_dt,
            )
        )
        res = conn.execute(update_stmt)
        if res.rowcount > 0:
            return

        # Row does not exist yet; insert with non-negative initial values
        initial_orders = max(delta["orders_count"], 0)
        initial_gross = max(delta["gross_sales"], Decimal("0.00"))
        initial_net = max(delta["net_sales"], Decimal("0.00"))
        initial_pending_orders = max(delta["pending_orders_count"], 0)
        initial_pending_sales = max(delta["pending_sales"], Decimal("0.00"))
        initial_cancelled_orders = max(delta["cancelled_orders_count"], 0)
        initial_cancelled_sales = max(delta["cancelled_sales"], Decimal("0.00"))

        if dialect_name == "postgresql":
            insert_sql = """
            INSERT INTO daily_tenant_metrics (
                id, tenant_id, metric_date, currency,
                orders_count, gross_sales, net_sales,
                pending_orders_count, pending_sales,
                cancelled_orders_count, cancelled_sales,
                created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :tenant_id, :metric_date, :currency,
                :init_orders, :init_gross, :init_net,
                :init_pending_orders, :init_pending_sales,
                :init_cancelled_orders, :init_cancelled_sales,
                clock_timestamp(), clock_timestamp()
            )
            ON CONFLICT (tenant_id, metric_date, currency)
            DO UPDATE SET
                orders_count = daily_tenant_metrics.orders_count + :orders_count,
                gross_sales = daily_tenant_metrics.gross_sales + :gross_sales,
                net_sales = daily_tenant_metrics.net_sales + :net_sales,
                pending_orders_count = daily_tenant_metrics.pending_orders_count + :pending_orders_count,
                pending_sales = daily_tenant_metrics.pending_sales + :pending_sales,
                cancelled_orders_count = daily_tenant_metrics.cancelled_orders_count + :cancelled_orders_count,
                cancelled_sales = daily_tenant_metrics.cancelled_sales + :cancelled_sales,
                updated_at = clock_timestamp();
            """
            insert_params = {
                "tenant_id": str(tenant_id),
                "metric_date": metric_date,
                "currency": currency,
                "now_dt": now_dt,
                **delta,
                "init_orders": initial_orders,
                "init_gross": initial_gross,
                "init_net": initial_net,
                "init_pending_orders": initial_pending_orders,
                "init_pending_sales": initial_pending_sales,
                "init_cancelled_orders": initial_cancelled_orders,
                "init_cancelled_sales": initial_cancelled_sales,
            }
            conn.execute(text(insert_sql), insert_params)
            return

        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "metric_date": metric_date,
            "currency": currency,
            "orders_count": initial_orders,
            "gross_sales": initial_gross,
            "net_sales": initial_net,
            "pending_orders_count": initial_pending_orders,
            "pending_sales": initial_pending_sales,
            "cancelled_orders_count": initial_cancelled_orders,
            "cancelled_sales": initial_cancelled_sales,
            "created_at": now_dt,
            "updated_at": now_dt,
        }
        stmt = sqlite_insert(DailyTenantMetric).values(**values)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["tenant_id", "metric_date", "currency"],
            set_={
                "orders_count": DailyTenantMetric.orders_count + delta["orders_count"],
                "gross_sales": DailyTenantMetric.gross_sales + delta["gross_sales"],
                "net_sales": DailyTenantMetric.net_sales + delta["net_sales"],
                "pending_orders_count": DailyTenantMetric.pending_orders_count + delta["pending_orders_count"],
                "pending_sales": DailyTenantMetric.pending_sales + delta["pending_sales"],
                "cancelled_orders_count": DailyTenantMetric.cancelled_orders_count + delta["cancelled_orders_count"],
                "cancelled_sales": DailyTenantMetric.cancelled_sales + delta["cancelled_sales"],
                "updated_at": now_dt,
            },
        )
        conn.execute(upsert_stmt)

    def _apply_product_metric_delta(
        self,
        conn: Connection,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        metric_date: Any,
        currency: str,
        delta: Dict[str, Any],
    ) -> None:
        """Apply incremental delta to daily_product_metrics using UPDATE-first pattern."""
        dialect_name = conn.dialect.name
        now_dt = datetime.now(timezone.utc)

        update_stmt = (
            update(DailyProductMetric)
            .where(
                DailyProductMetric.tenant_id == tenant_id,
                DailyProductMetric.product_id == product_id,
                DailyProductMetric.metric_date == metric_date,
                DailyProductMetric.currency == currency,
            )
            .values(
                units_sold_gross=DailyProductMetric.units_sold_gross + delta["units_sold_gross"],
                units_sold_net=DailyProductMetric.units_sold_net + delta["units_sold_net"],
                gross_sales=DailyProductMetric.gross_sales + delta["gross_sales"],
                net_sales=DailyProductMetric.net_sales + delta["net_sales"],
                pending_units=DailyProductMetric.pending_units + delta["pending_units"],
                pending_sales=DailyProductMetric.pending_sales + delta["pending_sales"],
                cancelled_units=DailyProductMetric.cancelled_units + delta["cancelled_units"],
                cancelled_sales=DailyProductMetric.cancelled_sales + delta["cancelled_sales"],
                orders_count=DailyProductMetric.orders_count + delta["orders_count"],
                updated_at=now_dt,
            )
        )
        res = conn.execute(update_stmt)
        if res.rowcount > 0:
            return

        initial_gross_units = max(delta["units_sold_gross"], 0)
        initial_net_units = max(delta["units_sold_net"], 0)
        initial_gross_sales = max(delta["gross_sales"], Decimal("0.00"))
        initial_net_sales = max(delta["net_sales"], Decimal("0.00"))
        initial_pending_units = max(delta["pending_units"], 0)
        initial_pending_sales = max(delta["pending_sales"], Decimal("0.00"))
        initial_cancelled_units = max(delta["cancelled_units"], 0)
        initial_cancelled_sales = max(delta["cancelled_sales"], Decimal("0.00"))
        initial_orders_cnt = max(delta["orders_count"], 0)

        if dialect_name == "postgresql":
            insert_sql = """
            INSERT INTO daily_product_metrics (
                id, tenant_id, product_id, metric_date, currency,
                units_sold_gross, units_sold_net,
                gross_sales, net_sales,
                pending_units, pending_sales,
                cancelled_units, cancelled_sales,
                orders_count,
                created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :tenant_id, :product_id, :metric_date, :currency,
                :init_gross_units, :init_net_units,
                :init_gross_sales, :init_net_sales,
                :init_pending_units, :init_pending_sales,
                :init_cancelled_units, :init_cancelled_sales,
                :init_orders_cnt,
                clock_timestamp(), clock_timestamp()
            )
            ON CONFLICT (tenant_id, product_id, metric_date, currency)
            DO UPDATE SET
                units_sold_gross = daily_product_metrics.units_sold_gross + :units_sold_gross,
                units_sold_net = daily_product_metrics.units_sold_net + :units_sold_net,
                gross_sales = daily_product_metrics.gross_sales + :gross_sales,
                net_sales = daily_product_metrics.net_sales + :net_sales,
                pending_units = daily_product_metrics.pending_units + :pending_units,
                pending_sales = daily_product_metrics.pending_sales + :pending_sales,
                cancelled_units = daily_product_metrics.cancelled_units + :cancelled_units,
                cancelled_sales = daily_product_metrics.cancelled_sales + :cancelled_sales,
                orders_count = daily_product_metrics.orders_count + :orders_count,
                updated_at = clock_timestamp();
            """
            insert_params = {
                "tenant_id": str(tenant_id),
                "product_id": str(product_id),
                "metric_date": metric_date,
                "currency": currency,
                "now_dt": now_dt,
                **delta,
                "init_gross_units": initial_gross_units,
                "init_net_units": initial_net_units,
                "init_gross_sales": initial_gross_sales,
                "init_net_sales": initial_net_sales,
                "init_pending_units": initial_pending_units,
                "init_pending_sales": initial_pending_sales,
                "init_cancelled_units": initial_cancelled_units,
                "init_cancelled_sales": initial_cancelled_sales,
                "init_orders_cnt": initial_orders_cnt,
            }
            conn.execute(text(insert_sql), insert_params)
            return

        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "product_id": product_id,
            "metric_date": metric_date,
            "currency": currency,
            "units_sold_gross": initial_gross_units,
            "units_sold_net": initial_net_units,
            "gross_sales": initial_gross_sales,
            "net_sales": initial_net_sales,
            "pending_units": initial_pending_units,
            "pending_sales": initial_pending_sales,
            "cancelled_units": initial_cancelled_units,
            "cancelled_sales": initial_cancelled_sales,
            "orders_count": initial_orders_cnt,
            "created_at": now_dt,
            "updated_at": now_dt,
        }
        stmt = sqlite_insert(DailyProductMetric).values(**values)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["tenant_id", "product_id", "metric_date", "currency"],
            set_={
                "units_sold_gross": DailyProductMetric.units_sold_gross + delta["units_sold_gross"],
                "units_sold_net": DailyProductMetric.units_sold_net + delta["units_sold_net"],
                "gross_sales": DailyProductMetric.gross_sales + delta["gross_sales"],
                "net_sales": DailyProductMetric.net_sales + delta["net_sales"],
                "pending_units": DailyProductMetric.pending_units + delta["pending_units"],
                "pending_sales": DailyProductMetric.pending_sales + delta["pending_sales"],
                "cancelled_units": DailyProductMetric.cancelled_units + delta["cancelled_units"],
                "cancelled_sales": DailyProductMetric.cancelled_sales + delta["cancelled_sales"],
                "orders_count": DailyProductMetric.orders_count + delta["orders_count"],
                "updated_at": now_dt,
            },
        )
        conn.execute(upsert_stmt)

    def _write_consumer_receipt(
        self,
        conn: Connection,
        event_id: uuid.UUID,
        tenant_id: uuid.UUID,
        event_type: str,
        order_id: uuid.UUID,
    ) -> None:
        """Record consumer receipt in analytics_consumer_events with ON CONFLICT DO NOTHING."""
        dialect_name = conn.dialect.name
        now_dt = datetime.now(timezone.utc)

        if dialect_name == "postgresql":
            sql = """
            INSERT INTO analytics_consumer_events (
                consumer_name, event_id, tenant_id, event_type, order_id, processed_at
            ) VALUES (
                :consumer_name, :event_id, :tenant_id, :event_type, :order_id, clock_timestamp()
            )
            ON CONFLICT (consumer_name, event_id) DO NOTHING;
            """
            conn.execute(
                text(sql),
                {
                    "consumer_name": self.consumer_name,
                    "event_id": str(event_id),
                    "tenant_id": str(tenant_id),
                    "event_type": event_type,
                    "order_id": str(order_id),
                },
            )
            return

        values = {
            "consumer_name": self.consumer_name,
            "event_id": event_id,
            "tenant_id": tenant_id,
            "event_type": event_type,
            "order_id": order_id,
            "processed_at": now_dt,
        }
        stmt = sqlite_insert(AnalyticsConsumerEvent).values(**values)
        conn.execute(stmt.on_conflict_do_nothing(index_elements=["consumer_name", "event_id"]))

    def _record_event_failure(
        self,
        conn: Connection,
        event: OutboxEvent,
        exc: Exception,
    ) -> None:
        """Record or increment failure attempts in analytics_dead_letter_events table."""
        now_dt = datetime.now(timezone.utc)
        error_msg = str(exc) or type(exc).__name__
        payload = event.payload if isinstance(event.payload, dict) else {}
        order_id_raw = payload.get("order_id")
        order_id: Optional[uuid.UUID] = None
        if order_id_raw:
            try:
                order_id = uuid.UUID(str(order_id_raw))
            except Exception:
                order_id = None

        error_details = {
            "exception_class": type(exc).__name__,
            "error_summary": error_msg[:500],
            "occurred_at": now_dt.isoformat(),
        }

        existing_attempt = conn.execute(
            select(AnalyticsDeadLetterEvent.attempts).where(
                AnalyticsDeadLetterEvent.consumer_name == self.consumer_name,
                AnalyticsDeadLetterEvent.event_id == event.id,
            )
        ).scalar()

        if existing_attempt is not None:
            new_attempts = existing_attempt + 1
            update_stmt = (
                update(AnalyticsDeadLetterEvent)
                .where(
                    AnalyticsDeadLetterEvent.consumer_name == self.consumer_name,
                    AnalyticsDeadLetterEvent.event_id == event.id,
                )
                .values(
                    attempts=new_attempts,
                    error_message=error_msg,
                    error_details=error_details,
                    last_failed_at=now_dt,
                    updated_at=now_dt,
                )
            )
            conn.execute(update_stmt)
            if new_attempts >= self.max_retries:
                logger.error(
                    "Worker [%s] event ID %s reached max retries (%d/%d) and is quarantined in DLQ.",
                    self.consumer_name,
                    event.id,
                    new_attempts,
                    self.max_retries,
                )
        else:
            insert_stmt = (
                sa.insert(AnalyticsDeadLetterEvent)
                .values(
                    id=uuid.uuid4(),
                    consumer_name=self.consumer_name,
                    event_id=event.id,
                    tenant_id=event.tenant_id,
                    event_type=event.event_type,
                    order_id=order_id,
                    error_message=error_msg,
                    error_details=error_details,
                    attempts=1,
                    first_failed_at=now_dt,
                    last_failed_at=now_dt,
                    created_at=now_dt,
                    updated_at=now_dt,
                )
            )
            conn.execute(insert_stmt)

    def _cleanup_dead_letter_on_success(self, conn: Connection, event_id: uuid.UUID) -> None:
        """Remove transient failure records if an event succeeded on retry."""
        conn.execute(
            sa.delete(AnalyticsDeadLetterEvent).where(
                AnalyticsDeadLetterEvent.consumer_name == self.consumer_name,
                AnalyticsDeadLetterEvent.event_id == event_id,
            )
        )

    def _broadcast_event(self, conn: Connection, event: OutboxEvent, order_id: Optional[uuid.UUID]) -> None:
        """Broadcast successfully processed event to in-memory broadcaster and PostgreSQL NOTIFY."""
        from app.analytics.broadcaster import broadcaster

        payload = event.payload if isinstance(event.payload, dict) else {}
        oid = order_id or (uuid.UUID(str(payload.get("order_id"))) if payload.get("order_id") else uuid.uuid4())
        ext_id = payload.get("external_order_id")
        status = payload.get("status")
        if not status:
            if event.event_type.endswith(".created"):
                status = "pending"
            elif event.event_type.endswith(".paid"):
                status = "paid"
            elif event.event_type.endswith(".fulfilled"):
                status = "fulfilled"
            elif event.event_type.endswith(".cancelled"):
                status = "cancelled"
            else:
                status = "pending"

        tot_amt = float(payload.get("total_amount", 0.0))
        curr = payload.get("currency", "USD")
        c_at = payload.get("occurred_at") or (
            event.created_at.isoformat() if hasattr(event.created_at, "isoformat") else str(event.created_at)
        )

        # In-process broadcast (instant local and test notification)
        broadcaster.publish_event(
            event_type=event.event_type,
            tenant_id=event.tenant_id,
            order_id=oid,
            status=status,
            total_amount=tot_amt,
            currency=curr,
            external_order_id=ext_id,
            created_at=c_at,
            event_id=str(event.id),
        )

        # PostgreSQL NOTIFY for cross-container event propagation
        if conn.dialect.name == "postgresql":
            try:
                msg = json.dumps(
                    {
                        "id": str(event.id),
                        "event_type": event.event_type,
                        "tenant_id": str(event.tenant_id),
                        "order_id": str(oid),
                        "external_order_id": ext_id,
                        "status": status,
                        "total_amount": tot_amt,
                        "currency": curr,
                        "created_at": c_at,
                    }
                )
                conn.execute(text("SELECT pg_notify('aggrix_events', :payload)"), {"payload": msg})
            except Exception as pg_err:
                logger.debug("pg_notify skipped: %s", pg_err)

    def get_dead_letter_events(
        self,
        conn: Connection,
        tenant_id: Optional[uuid.UUID] = None,
        quarantined_only: bool = True,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query dead-letter records for inspection.

        Args:
            conn: Active database connection.
            tenant_id: Optional filter for a specific tenant.
            quarantined_only: If True, only returns events with attempts >= max_retries.
            limit: Maximum records to return.

        Returns:
            List of dictionaries representing dead-letter event records.
        """
        stmt = (
            select(
                AnalyticsDeadLetterEvent.id,
                AnalyticsDeadLetterEvent.consumer_name,
                AnalyticsDeadLetterEvent.event_id,
                AnalyticsDeadLetterEvent.tenant_id,
                AnalyticsDeadLetterEvent.event_type,
                AnalyticsDeadLetterEvent.order_id,
                AnalyticsDeadLetterEvent.error_message,
                AnalyticsDeadLetterEvent.attempts,
                AnalyticsDeadLetterEvent.first_failed_at,
                AnalyticsDeadLetterEvent.last_failed_at,
            )
            .where(AnalyticsDeadLetterEvent.consumer_name == self.consumer_name)
        )
        if tenant_id:
            stmt = stmt.where(AnalyticsDeadLetterEvent.tenant_id == tenant_id)
        if quarantined_only:
            stmt = stmt.where(AnalyticsDeadLetterEvent.attempts >= self.max_retries)
        stmt = stmt.order_by(AnalyticsDeadLetterEvent.last_failed_at.desc()).limit(limit)

        rows = conn.execute(stmt).fetchall()
        return [
            {
                "id": r[0],
                "consumer_name": r[1],
                "event_id": r[2],
                "tenant_id": r[3],
                "event_type": r[4],
                "order_id": r[5],
                "error_message": r[6],
                "attempts": r[7],
                "first_failed_at": r[8],
                "last_failed_at": r[9],
            }
            for r in rows
        ]

    def replay_dead_letter_event(
        self,
        conn: Connection,
        event_id: uuid.UUID,
    ) -> bool:
        """Explicitly replay a dead-letter event from outbox_events.

        Acquires advisory lock, fetches the corresponding OutboxEvent,
        and re-runs _process_single_event within a transaction savepoint.
        If processing succeeds:
          - Automatically removes the dead-letter record via _cleanup_dead_letter_on_success.
          - The receipt is created in analytics_consumer_events.
          - Returns True (or False if skipped because receipt already existed).
        If processing fails:
          - Updates the dead-letter record via _record_event_failure.
          - Re-raises the exception.
        """
        acquire_advisory_lock(conn, wait=True)

        stmt = select(
            OutboxEvent.id,
            OutboxEvent.tenant_id,
            OutboxEvent.event_type,
            OutboxEvent.payload,
            OutboxEvent.created_at,
            OutboxEvent.processed_at,
        ).where(OutboxEvent.id == event_id)
        row = conn.execute(stmt).fetchone()
        if not row:
            raise ValueError(f"Outbox event with ID '{event_id}' not found.")

        payload_data = row[3]
        if isinstance(payload_data, str):
            try:
                payload_data = json.loads(payload_data)
            except Exception:
                payload_data = {}

        event = OutboxEvent(
            id=row[0] if isinstance(row[0], uuid.UUID) else uuid.UUID(str(row[0])),
            tenant_id=row[1] if isinstance(row[1], uuid.UUID) else uuid.UUID(str(row[1])),
            event_type=row[2],
            payload=payload_data,
            created_at=row[4],
            processed_at=row[5],
        )

        sp = conn.begin_nested()
        try:
            was_processed = self._process_single_event(conn, event)
            if was_processed:
                self._cleanup_dead_letter_on_success(conn, event.id)
            sp.commit()
            return was_processed
        except Exception as exc:
            sp.rollback()
            self._record_event_failure(conn, event, exc)
            raise

    def reset_dead_letter_attempts(
        self,
        conn: Connection,
        event_ids: Optional[List[uuid.UUID]] = None,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Reset failed attempt counters to 0, enabling the background worker daemon to re-poll them.

        Returns:
            Number of dead-letter records reset.
        """
        stmt = (
            update(AnalyticsDeadLetterEvent)
            .where(AnalyticsDeadLetterEvent.consumer_name == self.consumer_name)
            .values(attempts=0, updated_at=datetime.now(timezone.utc))
        )
        if event_ids:
            stmt = stmt.where(AnalyticsDeadLetterEvent.event_id.in_(event_ids))
        if tenant_id:
            stmt = stmt.where(AnalyticsDeadLetterEvent.tenant_id == tenant_id)

        result = conn.execute(stmt)
        return result.rowcount

    def replay_dead_letter_batch(
        self,
        conn: Connection,
        tenant_id: Optional[uuid.UUID] = None,
        limit: int = 100,
    ) -> Tuple[int, int, List[str]]:
        """Replay all quarantined dead-letter events up to limit.

        Returns:
            Tuple of (success_count, failure_count, list_of_error_messages).
        """
        events = self.get_dead_letter_events(conn, tenant_id=tenant_id, quarantined_only=True, limit=limit)
        success_count = 0
        failure_count = 0
        errors: List[str] = []

        for dlq in events:
            eid = dlq["event_id"]
            try:
                self.replay_dead_letter_event(conn, eid)
                success_count += 1
            except Exception as exc:
                failure_count += 1
                errors.append(f"Event {eid}: {exc}")

        return success_count, failure_count, errors


def run_worker_daemon(
    engine: Optional[Engine] = None,
    consumer_name: Optional[str] = None,
    batch_size: Optional[int] = None,
    poll_interval_seconds: Optional[float] = None,
    max_retries: Optional[int] = None,
    stop_event: Optional[threading.Event] = None,
    max_batches: Optional[int] = None,
) -> int:
    """Run the incremental aggregation worker as a continuous background daemon.

    Continuously polls and processes outbox events in transactional batches.
    Supports graceful SIGINT/SIGTERM shutdown, handles advisory lock conflicts with backoff,
    and avoids busy-looping when the queue is empty.

    Args:
        engine: Optional SQLAlchemy Engine.
        consumer_name: Consumer tracking identifier.
        batch_size: Number of events to process per batch.
        poll_interval_seconds: Sleep duration when queue is empty.
        max_retries: Max failure attempts before dead-lettering.
        stop_event: Optional threading.Event to signal daemon shutdown.
        max_batches: Optional maximum number of batches to process before exiting.

    Returns:
        Total number of events processed during the daemon's runtime.
    """
    worker = IncrementalAggregationWorker(
        engine=engine,
        consumer_name=consumer_name,
        batch_size=batch_size,
        polling_interval_seconds=poll_interval_seconds,
        max_retries=max_retries,
    )

    logger.info(
        "Starting AGGRIX Incremental Aggregation Worker daemon "
        "(consumer=%s, batch_size=%d, interval=%.2fs, max_retries=%d)",
        worker.consumer_name,
        worker.batch_size,
        worker.polling_interval_seconds,
        worker.max_retries,
    )

    shutdown_flag = threading.Event()

    def _handle_signal(signum: int, frame: Any) -> None:
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.info(
            "Worker daemon received shutdown signal %s (%d). Completing active batch and shutting down...",
            sig_name,
            signum,
        )
        shutdown_flag.set()

    old_sigint = None
    old_sigterm = None
    try:
        old_sigint = signal.signal(signal.SIGINT, _handle_signal)
        old_sigterm = signal.signal(signal.SIGTERM, _handle_signal)
    except (ValueError, AttributeError):
        pass

    batches_run = 0
    total_processed = 0

    try:
        while not shutdown_flag.is_set() and not (stop_event and stop_event.is_set()):
            if max_batches is not None and batches_run >= max_batches:
                logger.info("Worker daemon reached max_batches limit (%d). Terminating loop.", max_batches)
                break

            try:
                res = worker.process_batch()
                batches_run += 1
                total_processed += res.events_processed

                if res.events_polled > 0:
                    # Queue has work; yield briefly or continue immediately
                    continue

                # Queue is empty: sleep for polling_interval_seconds without busy-looping
                sleep_time = worker.polling_interval_seconds
                shutdown_flag.wait(timeout=sleep_time)
                if stop_event:
                    stop_event.wait(timeout=0.01)

            except AnalyticsLockConflictError:
                logger.warning(
                    "Worker daemon encountered advisory lock conflict (backfill or another worker active). Backing off for %.1fs...",
                    worker.polling_interval_seconds * 2,
                )
                shutdown_flag.wait(timeout=worker.polling_interval_seconds * 2)
            except Exception as exc:
                logger.error(
                    "Unexpected error in worker daemon loop: %s. Backing off for %.1fs...",
                    exc,
                    worker.polling_interval_seconds,
                    exc_info=True,
                )
                shutdown_flag.wait(timeout=worker.polling_interval_seconds)

    finally:
        try:
            if old_sigint is not None:
                signal.signal(signal.SIGINT, old_sigint)
            if old_sigterm is not None:
                signal.signal(signal.SIGTERM, old_sigterm)
        except (ValueError, AttributeError):
            pass
        logger.info(
            "Worker daemon stopped. Total events processed: %d across %d batches.",
            total_processed,
            batches_run,
        )

    return total_processed


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_worker_daemon()
