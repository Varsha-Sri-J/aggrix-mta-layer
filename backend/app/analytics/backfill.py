"""Historical Backfill Service for AGGRIX Analytics Engine.

Provides atomic, idempotent calculation and population of:
1. daily_tenant_metrics
2. daily_product_metrics
3. analytics_consumer_events

Core Architectural Guarantees:
- PostgreSQL REPEATABLE READ snapshot consistency ensuring order data and outbox event receipts
  are evaluated against the exact same point-in-time database snapshot.
- Full tenant-local IANA timezone preservation (DATE(o.created_at AT TIME ZONE t.timezone)).
- Strict currency segregation (no currency mixing, no FX conversions).
- Immutable accounting identity: gross_sales == net_sales + pending_sales + cancelled_sales.
- Complete idempotency and safe rerun capability via database unique constraint upserts.
- Atomic commit & rollback (all-or-nothing transactional boundary).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.analytics.coordination import (
    AGGRIX_ANALYTICS_LOCK_ID,
    SUPPORTED_ORDER_EVENT_TYPES,
    AnalyticsLockConflictError,
    acquire_advisory_lock,
)
from app.database.connection import create_database_engine, engine as default_engine
from app.models.analytics_consumer_event import AnalyticsConsumerEvent
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillResult:
    """Structured report returned upon completion of a backfill execution."""

    tenant_metrics_count: int
    product_metrics_count: int
    consumer_events_count: int
    orders_processed: int
    order_items_processed: int
    gross_sales_total: Decimal
    net_sales_total: Decimal
    pending_sales_total: Decimal
    cancelled_sales_total: Decimal
    duration_seconds: float
    tenant_id: Optional[uuid.UUID] = None
    consumer_name: str = "analytics_worker"

    def verify_accounting_identity(self) -> bool:
        """Verify that gross_sales == net_sales + pending_sales + cancelled_sales."""
        return self.gross_sales_total == (
            self.net_sales_total + self.pending_sales_total + self.cancelled_sales_total
        )


class HistoricalBackfillService:
    """Historical backfill orchestration engine for AGGRIX."""

    def __init__(self, consumer_name: str = "analytics_worker") -> None:
        """Initialize backfill service with default consumer name."""
        self.consumer_name = consumer_name

    def run(
        self,
        session: Optional[Session] = None,
        engine: Optional[Engine] = None,
        tenant_id: Optional[Union[uuid.UUID, str]] = None,
        consumer_name: Optional[str] = None,
        wait_for_lock: bool = True,
    ) -> BackfillResult:
        """Execute the historical backfill process atomically.

        Args:
            session: Optional existing SQLAlchemy Session (e.g. for testing within transactions).
            engine: Optional SQLAlchemy Engine. Defaults to application database engine.
            tenant_id: Optional UUID to restrict backfill to a single tenant.
            consumer_name: Optional name for tracking event receipts (defaults to instance name).
            wait_for_lock: If True (default), wait for any active aggregation lock to be released.
                          If False, fail fast with AnalyticsLockConflictError if lock is held.

        Returns:
            BackfillResult summarizing processed entities and aggregated financials.
        """
        start_time = time.perf_counter()
        target_consumer = consumer_name or self.consumer_name
        parsed_tenant_id = uuid.UUID(str(tenant_id)) if tenant_id is not None else None

        if session is not None:
            # Use connection from caller-managed session (e.g., test transaction)
            conn = session.connection()
            nested = conn.begin_nested()
            try:
                result = self._execute_on_connection(
                    conn, parsed_tenant_id, target_consumer, start_time, wait_for_lock=wait_for_lock
                )
                nested.commit()
                return result
            except Exception:
                nested.rollback()
                raise

        db_engine = engine or default_engine or create_database_engine()
        iso_level = (
            "REPEATABLE READ"
            if db_engine.dialect.name == "postgresql"
            else "SERIALIZABLE"
        )

        with db_engine.connect().execution_options(isolation_level=iso_level) as conn:
            with conn.begin():
                result = self._execute_on_connection(
                    conn, parsed_tenant_id, target_consumer, start_time, wait_for_lock=wait_for_lock
                )
                return result

    def _execute_on_connection(
        self,
        conn: Connection,
        tenant_id: Optional[uuid.UUID],
        consumer_name: str,
        start_time: float,
        wait_for_lock: bool = True,
    ) -> BackfillResult:
        """Route to dialect-optimized implementation and compile execution metrics."""
        # 1. Acquire transaction-scoped advisory lock to coordinate with worker processes
        acquire_advisory_lock(conn, wait=wait_for_lock)

        dialect_name = conn.dialect.name

        if dialect_name == "postgresql":
            self._run_postgresql(conn, tenant_id, consumer_name)
        else:
            self._run_generic(conn, tenant_id, consumer_name)

        # Retrieve summary metrics within the same snapshot boundary
        return self._compile_metrics(conn, tenant_id, consumer_name, start_time)

    def _run_postgresql(
        self,
        conn: Connection,
        tenant_id: Optional[uuid.UUID],
        consumer_name: str,
    ) -> None:
        """High-performance set-based aggregation using PostgreSQL SQL and REPEATABLE READ snapshot."""
        tenant_filter_order = "WHERE o.tenant_id = :tenant_id" if tenant_id else ""
        tenant_filter_item = "WHERE oi.tenant_id = :tenant_id" if tenant_id else ""
        tenant_filter_event = "AND oe.tenant_id = :tenant_id" if tenant_id else ""
        params: Dict[str, Any] = {"consumer_name": consumer_name}
        if tenant_id:
            params["tenant_id"] = str(tenant_id)

        # 1. Upsert daily_tenant_metrics
        sql_tenant_metrics = f"""
        INSERT INTO daily_tenant_metrics (
            id,
            tenant_id,
            metric_date,
            currency,
            orders_count,
            gross_sales,
            net_sales,
            pending_orders_count,
            pending_sales,
            cancelled_orders_count,
            cancelled_sales,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            o.tenant_id,
            DATE(o.created_at AT TIME ZONE COALESCE(t.timezone, 'UTC')) AS metric_date,
            o.currency,
            COUNT(o.id) AS orders_count,
            COALESCE(SUM(o.total_amount), 0) AS gross_sales,
            COALESCE(SUM(CASE WHEN o.status IN ('paid', 'fulfilled') THEN o.total_amount ELSE 0 END), 0) AS net_sales,
            COALESCE(SUM(CASE WHEN o.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_orders_count,
            COALESCE(SUM(CASE WHEN o.status = 'pending' THEN o.total_amount ELSE 0 END), 0) AS pending_sales,
            COALESCE(SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_orders_count,
            COALESCE(SUM(CASE WHEN o.status = 'cancelled' THEN o.total_amount ELSE 0 END), 0) AS cancelled_sales,
            clock_timestamp(),
            clock_timestamp()
        FROM orders o
        JOIN tenants t ON t.id = o.tenant_id
        {tenant_filter_order}
        GROUP BY o.tenant_id, DATE(o.created_at AT TIME ZONE COALESCE(t.timezone, 'UTC')), o.currency
        ON CONFLICT (tenant_id, metric_date, currency)
        DO UPDATE SET
            orders_count = EXCLUDED.orders_count,
            gross_sales = EXCLUDED.gross_sales,
            net_sales = EXCLUDED.net_sales,
            pending_orders_count = EXCLUDED.pending_orders_count,
            pending_sales = EXCLUDED.pending_sales,
            cancelled_orders_count = EXCLUDED.cancelled_orders_count,
            cancelled_sales = EXCLUDED.cancelled_sales,
            updated_at = EXCLUDED.updated_at;
        """
        conn.execute(text(sql_tenant_metrics), params)

        # 2. Upsert daily_product_metrics
        sql_product_metrics = f"""
        INSERT INTO daily_product_metrics (
            id,
            tenant_id,
            product_id,
            metric_date,
            currency,
            units_sold_gross,
            units_sold_net,
            gross_sales,
            net_sales,
            pending_units,
            pending_sales,
            cancelled_units,
            cancelled_sales,
            orders_count,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            oi.tenant_id,
            oi.product_id,
            DATE(o.created_at AT TIME ZONE COALESCE(t.timezone, 'UTC')) AS metric_date,
            o.currency,
            COALESCE(SUM(oi.quantity), 0) AS units_sold_gross,
            COALESCE(SUM(CASE WHEN o.status IN ('paid', 'fulfilled') THEN oi.quantity ELSE 0 END), 0) AS units_sold_net,
            COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS gross_sales,
            COALESCE(SUM(CASE WHEN o.status IN ('paid', 'fulfilled') THEN (oi.quantity * oi.unit_price) ELSE 0 END), 0) AS net_sales,
            COALESCE(SUM(CASE WHEN o.status = 'pending' THEN oi.quantity ELSE 0 END), 0) AS pending_units,
            COALESCE(SUM(CASE WHEN o.status = 'pending' THEN (oi.quantity * oi.unit_price) ELSE 0 END), 0) AS pending_sales,
            COALESCE(SUM(CASE WHEN o.status = 'cancelled' THEN oi.quantity ELSE 0 END), 0) AS cancelled_units,
            COALESCE(SUM(CASE WHEN o.status = 'cancelled' THEN (oi.quantity * oi.unit_price) ELSE 0 END), 0) AS cancelled_sales,
            COUNT(DISTINCT oi.order_id) AS orders_count,
            clock_timestamp(),
            clock_timestamp()
        FROM order_items oi
        JOIN orders o ON o.tenant_id = oi.tenant_id AND o.id = oi.order_id
        JOIN tenants t ON t.id = oi.tenant_id
        {tenant_filter_item}
        GROUP BY oi.tenant_id, oi.product_id, DATE(o.created_at AT TIME ZONE COALESCE(t.timezone, 'UTC')), o.currency
        ON CONFLICT (tenant_id, product_id, metric_date, currency)
        DO UPDATE SET
            units_sold_gross = EXCLUDED.units_sold_gross,
            units_sold_net = EXCLUDED.units_sold_net,
            gross_sales = EXCLUDED.gross_sales,
            net_sales = EXCLUDED.net_sales,
            pending_units = EXCLUDED.pending_units,
            pending_sales = EXCLUDED.pending_sales,
            cancelled_units = EXCLUDED.cancelled_units,
            cancelled_sales = EXCLUDED.cancelled_sales,
            orders_count = EXCLUDED.orders_count,
            updated_at = EXCLUDED.updated_at;
        """
        conn.execute(text(sql_product_metrics), params)

        # 3. Insert outbox events into analytics_consumer_events (filtered strictly to supported order event types)
        sql_consumer_events = f"""
        INSERT INTO analytics_consumer_events (
            consumer_name,
            event_id,
            tenant_id,
            event_type,
            order_id,
            processed_at
        )
        SELECT
            :consumer_name,
            oe.id,
            oe.tenant_id,
            oe.event_type,
            (oe.payload->>'order_id')::uuid,
            clock_timestamp()
        FROM outbox_events oe
        WHERE oe.event_type IN ('order.created', 'order.paid', 'order.fulfilled', 'order.cancelled')
          AND oe.payload->>'order_id' IS NOT NULL
        {tenant_filter_event}
        ON CONFLICT (consumer_name, event_id) DO NOTHING;
        """
        conn.execute(text(sql_consumer_events), params)

    def _run_generic(
        self,
        conn: Connection,
        tenant_id: Optional[uuid.UUID],
        consumer_name: str,
    ) -> None:
        """Generic aggregation implementation supporting SQLite for lightweight in-memory testing."""
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        # 1. Fetch tenants and build timezone mapping
        tenant_stmt = select(Tenant.id, Tenant.timezone)
        if tenant_id:
            tenant_stmt = tenant_stmt.where(Tenant.id == tenant_id)
        tenant_rows = conn.execute(tenant_stmt).fetchall()
        tenant_timezones: Dict[uuid.UUID, ZoneInfo] = {}
        for tid, tz_str in tenant_rows:
            try:
                tenant_timezones[tid] = ZoneInfo(tz_str or "UTC")
            except Exception:
                tenant_timezones[tid] = ZoneInfo("UTC")

        # 2. Fetch and aggregate orders
        order_stmt = select(
            Order.id,
            Order.tenant_id,
            Order.currency,
            Order.status,
            Order.total_amount,
            Order.created_at,
        )
        if tenant_id:
            order_stmt = order_stmt.where(Order.tenant_id == tenant_id)
        order_rows = conn.execute(order_stmt).fetchall()

        tenant_aggregates: Dict[tuple, Dict[str, Any]] = {}
        order_local_dates: Dict[uuid.UUID, Any] = {}
        order_currencies: Dict[uuid.UUID, str] = {}
        order_statuses: Dict[uuid.UUID, str] = {}

        for oid, otid, ocurrency, ostatus, ototal, ocreated in order_rows:
            tz = tenant_timezones.get(otid, ZoneInfo("UTC"))
            dt = ocreated if ocreated.tzinfo else ocreated.replace(tzinfo=timezone.utc)
            local_date = dt.astimezone(tz).date()

            order_local_dates[oid] = local_date
            order_currencies[oid] = ocurrency
            order_statuses[oid] = ostatus

            group_key = (otid, local_date, ocurrency)
            if group_key not in tenant_aggregates:
                tenant_aggregates[group_key] = {
                    "tenant_id": otid,
                    "metric_date": local_date,
                    "currency": ocurrency,
                    "orders_count": 0,
                    "gross_sales": Decimal("0.00"),
                    "net_sales": Decimal("0.00"),
                    "pending_orders_count": 0,
                    "pending_sales": Decimal("0.00"),
                    "cancelled_orders_count": 0,
                    "cancelled_sales": Decimal("0.00"),
                }

            agg = tenant_aggregates[group_key]
            agg["orders_count"] += 1
            agg["gross_sales"] += Decimal(str(ototal))

            if ostatus in ("paid", "fulfilled"):
                agg["net_sales"] += Decimal(str(ototal))
            elif ostatus == "pending":
                agg["pending_orders_count"] += 1
                agg["pending_sales"] += Decimal(str(ototal))
            elif ostatus == "cancelled":
                agg["cancelled_orders_count"] += 1
                agg["cancelled_sales"] += Decimal(str(ototal))

        # Upsert daily_tenant_metrics
        for agg in tenant_aggregates.values():
            now_dt = datetime.now(timezone.utc)
            values = {
                "id": uuid.uuid4(),
                "created_at": now_dt,
                "updated_at": now_dt,
                **agg,
            }
            stmt = sqlite_insert(DailyTenantMetric).values(**values)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "metric_date", "currency"],
                set_={
                    "orders_count": stmt.excluded.orders_count,
                    "gross_sales": stmt.excluded.gross_sales,
                    "net_sales": stmt.excluded.net_sales,
                    "pending_orders_count": stmt.excluded.pending_orders_count,
                    "pending_sales": stmt.excluded.pending_sales,
                    "cancelled_orders_count": stmt.excluded.cancelled_orders_count,
                    "cancelled_sales": stmt.excluded.cancelled_sales,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            conn.execute(upsert_stmt)

        # 3. Fetch and aggregate order items
        item_stmt = select(
            OrderItem.tenant_id,
            OrderItem.order_id,
            OrderItem.product_id,
            OrderItem.quantity,
            OrderItem.unit_price,
        )
        if tenant_id:
            item_stmt = item_stmt.where(OrderItem.tenant_id == tenant_id)
        item_rows = conn.execute(item_stmt).fetchall()

        product_aggregates: Dict[tuple, Dict[str, Any]] = {}
        for itid, ioid, ipid, iqty, iprice in item_rows:
            local_date = order_local_dates.get(ioid)
            currency = order_currencies.get(ioid, "USD")
            status = order_statuses.get(ioid, "pending")
            if not local_date:
                continue

            item_total = Decimal(str(iqty)) * Decimal(str(iprice))
            group_key = (itid, ipid, local_date, currency)

            if group_key not in product_aggregates:
                product_aggregates[group_key] = {
                    "tenant_id": itid,
                    "product_id": ipid,
                    "metric_date": local_date,
                    "currency": currency,
                    "units_sold_gross": 0,
                    "units_sold_net": 0,
                    "gross_sales": Decimal("0.00"),
                    "net_sales": Decimal("0.00"),
                    "pending_units": 0,
                    "pending_sales": Decimal("0.00"),
                    "cancelled_units": 0,
                    "cancelled_sales": Decimal("0.00"),
                    "_order_ids": set(),
                }

            agg = product_aggregates[group_key]
            agg["units_sold_gross"] += iqty
            agg["gross_sales"] += item_total
            agg["_order_ids"].add(ioid)

            if status in ("paid", "fulfilled"):
                agg["units_sold_net"] += iqty
                agg["net_sales"] += item_total
            elif status == "pending":
                agg["pending_units"] += iqty
                agg["pending_sales"] += item_total
            elif status == "cancelled":
                agg["cancelled_units"] += iqty
                agg["cancelled_sales"] += item_total

        # Upsert daily_product_metrics
        for agg in product_aggregates.values():
            orders_cnt = len(agg.pop("_order_ids"))
            agg["orders_count"] = orders_cnt
            now_dt = datetime.now(timezone.utc)
            values = {
                "id": uuid.uuid4(),
                "created_at": now_dt,
                "updated_at": now_dt,
                **agg,
            }
            stmt = sqlite_insert(DailyProductMetric).values(**values)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "product_id", "metric_date", "currency"],
                set_={
                    "units_sold_gross": stmt.excluded.units_sold_gross,
                    "units_sold_net": stmt.excluded.units_sold_net,
                    "gross_sales": stmt.excluded.gross_sales,
                    "net_sales": stmt.excluded.net_sales,
                    "pending_units": stmt.excluded.pending_units,
                    "pending_sales": stmt.excluded.pending_sales,
                    "cancelled_units": stmt.excluded.cancelled_units,
                    "cancelled_sales": stmt.excluded.cancelled_sales,
                    "orders_count": stmt.excluded.orders_count,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            conn.execute(upsert_stmt)

        # 4. Process outbox events (filtered strictly to supported order event types)
        event_stmt = select(
            OutboxEvent.id,
            OutboxEvent.tenant_id,
            OutboxEvent.event_type,
            OutboxEvent.payload,
        ).where(OutboxEvent.event_type.in_(SUPPORTED_ORDER_EVENT_TYPES))
        if tenant_id:
            event_stmt = event_stmt.where(OutboxEvent.tenant_id == tenant_id)
        event_rows = conn.execute(event_stmt).fetchall()

        now_dt = datetime.now(timezone.utc)
        for eid, etid, etype, epayload in event_rows:
            order_id_raw = epayload.get("order_id") if isinstance(epayload, dict) else None
            if not order_id_raw:
                continue
            try:
                order_uuid = uuid.UUID(str(order_id_raw))
            except Exception:
                continue

            values = {
                "consumer_name": consumer_name,
                "event_id": eid,
                "tenant_id": etid,
                "event_type": etype,
                "order_id": order_uuid,
                "processed_at": now_dt,
            }
            stmt = sqlite_insert(AnalyticsConsumerEvent).values(**values)
            conn.execute(
                stmt.on_conflict_do_nothing(
                    index_elements=["consumer_name", "event_id"]
                )
            )

    def _compile_metrics(
        self,
        conn: Connection,
        tenant_id: Optional[uuid.UUID],
        consumer_name: str,
        start_time: float,
    ) -> BackfillResult:
        """Compile execution metrics from database tables inside the current snapshot."""
        # Tenant metrics summary
        tenant_query = select(
            func.count(DailyTenantMetric.id).label("metric_rows"),
            func.coalesce(func.sum(DailyTenantMetric.orders_count), 0).label("orders_count"),
            func.coalesce(func.sum(DailyTenantMetric.gross_sales), 0).label("gross_sales"),
            func.coalesce(func.sum(DailyTenantMetric.net_sales), 0).label("net_sales"),
            func.coalesce(func.sum(DailyTenantMetric.pending_sales), 0).label("pending_sales"),
            func.coalesce(func.sum(DailyTenantMetric.cancelled_sales), 0).label("cancelled_sales"),
        )
        if tenant_id:
            tenant_query = tenant_query.where(DailyTenantMetric.tenant_id == tenant_id)
        t_row = conn.execute(tenant_query).fetchone()

        # Product metrics row count
        product_query = select(func.count(DailyProductMetric.id))
        if tenant_id:
            product_query = product_query.where(DailyProductMetric.tenant_id == tenant_id)
        p_count = conn.execute(product_query).scalar() or 0

        # Consumer events recorded
        events_query = select(func.count(AnalyticsConsumerEvent.event_id)).where(
            AnalyticsConsumerEvent.consumer_name == consumer_name
        )
        if tenant_id:
            events_query = events_query.where(AnalyticsConsumerEvent.tenant_id == tenant_id)
        e_count = conn.execute(events_query).scalar() or 0

        # Total order items
        items_query = select(func.count(OrderItem.id))
        if tenant_id:
            items_query = items_query.where(OrderItem.tenant_id == tenant_id)
        items_count = conn.execute(items_query).scalar() or 0

        duration = time.perf_counter() - start_time

        return BackfillResult(
            tenant_metrics_count=t_row[0] if t_row else 0,
            product_metrics_count=p_count,
            consumer_events_count=e_count,
            orders_processed=t_row[1] if t_row else 0,
            order_items_processed=items_count,
            gross_sales_total=Decimal(str(t_row[2])) if t_row else Decimal("0.00"),
            net_sales_total=Decimal(str(t_row[3])) if t_row else Decimal("0.00"),
            pending_sales_total=Decimal(str(t_row[4])) if t_row else Decimal("0.00"),
            cancelled_sales_total=Decimal(str(t_row[5])) if t_row else Decimal("0.00"),
            duration_seconds=duration,
            tenant_id=tenant_id,
            consumer_name=consumer_name,
        )


def main() -> None:
    """CLI entrypoint for running the historical backfill service."""
    parser = argparse.ArgumentParser(
        description="AGGRIX Analytics Historical Backfill Engine"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Optional tenant UUID to restrict backfill to a single tenant.",
    )
    parser.add_argument(
        "--consumer-name",
        type=str,
        default="analytics_worker",
        help="Consumer identifier for tracking outbox receipts.",
    )
    parser.add_argument(
        "--no-wait-lock",
        action="store_true",
        help="Fail fast if aggregation advisory lock is held by another process.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("Starting AGGRIX Historical Backfill...")

    service = HistoricalBackfillService(consumer_name=args.consumer_name)
    result = service.run(tenant_id=args.tenant_id, wait_for_lock=not args.no_wait_lock)

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)
    logger.info("Execution duration:       %.3f seconds", result.duration_seconds)
    logger.info("Orders processed:         %d", result.orders_processed)
    logger.info("Order items processed:    %d", result.order_items_processed)
    logger.info("Tenant metric rows:       %d", result.tenant_metrics_count)
    logger.info("Product metric rows:      %d", result.product_metrics_count)
    logger.info("Consumer events recorded: %d", result.consumer_events_count)
    logger.info("-" * 60)
    logger.info("Gross Sales Total:        $%s", result.gross_sales_total)
    logger.info("Net Sales Total:          $%s", result.net_sales_total)
    logger.info("Pending Sales Total:      $%s", result.pending_sales_total)
    logger.info("Cancelled Sales Total:    $%s", result.cancelled_sales_total)
    logger.info("-" * 60)
    logger.info("Accounting Identity Check: %s", "PASSED" if result.verify_accounting_identity() else "FAILED")
    logger.info("=" * 60)

    if not result.verify_accounting_identity():
        logger.error("FATAL: Accounting identity check failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
