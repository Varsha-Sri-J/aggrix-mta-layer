"""Comprehensive unit and integration tests for the AGGRIX Historical Backfill Engine."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics.backfill import BackfillResult, HistoricalBackfillService
from app.analytics.coordination import (
    AGGRIX_ANALYTICS_LOCK_ID,
    AnalyticsLockConflictError,
    acquire_advisory_lock,
)
from app.database.connection import create_database_engine
from app.models.analytics_consumer_event import AnalyticsConsumerEvent
from app.models.customer import Customer
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant
from tests.conftest import is_postgres_available


def _create_tenant(
    session: Session,
    name: str = "Test Store",
    timezone_name: str = "UTC",
    domain: Optional[str] = None,
) -> Tenant:
    """Helper to create and flush a Tenant with explicit timezone."""
    tenant = Tenant(
        name=name,
        domain=domain or f"{uuid.uuid4().hex[:8]}.example.com",
        timezone=timezone_name,
    )
    session.add(tenant)
    session.flush()
    return tenant


def _create_product(
    session: Session,
    tenant_id: uuid.UUID,
    name: str = "Test Product",
    price: Decimal = Decimal("50.00"),
    currency: str = "USD",
) -> Product:
    """Helper to create and flush a Product."""
    product = Product(
        tenant_id=tenant_id,
        sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
        name=name,
        price=price,
        currency=currency,
    )
    session.add(product)
    session.flush()
    return product


def _create_customer(session: Session, tenant_id: uuid.UUID) -> Customer:
    """Helper to create and flush a Customer."""
    customer = Customer(
        tenant_id=tenant_id,
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        name="Test Customer",
    )
    session.add(customer)
    session.flush()
    return customer


def _create_order_with_item(
    session: Session,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int = 1,
    unit_price: Decimal = Decimal("50.00"),
    status: str = "pending",
    currency: str = "USD",
    created_at: Optional[datetime] = None,
) -> tuple[Order, OrderItem, OutboxEvent]:
    """Helper to create an Order, OrderItem, and OutboxEvent transactionally."""
    total_amount = Decimal(str(quantity)) * Decimal(str(unit_price))
    order = Order(
        tenant_id=tenant_id,
        customer_id=customer_id,
        external_order_id=f"ORD-{uuid.uuid4().hex[:8]}",
        total_amount=total_amount,
        currency=currency,
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(order)
    session.flush()

    item = OrderItem(
        tenant_id=tenant_id,
        order_id=order.id,
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        created_at=order.created_at,
    )
    session.add(item)

    event_type = "order.created" if status == "pending" else f"order.{status}"
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        payload={
            "order_id": str(order.id),
            "tenant_id": str(tenant_id),
            "status": status,
            "total_amount": str(total_amount),
            "currency": currency,
        },
        created_at=order.created_at,
    )
    session.add(event)
    session.flush()

    return order, item, event


# ==============================================================================
# TEST 1: Pending Orders
# ==============================================================================
def test_backfill_pending_orders(session: Session) -> None:
    """Verify that pending orders populate pending_orders_count and pending_sales but net_sales = 0."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    product = _create_product(session, tenant.id, price=Decimal("100.00"))

    _create_order_with_item(
        session,
        tenant.id,
        customer.id,
        product.id,
        quantity=2,
        unit_price=Decimal("100.00"),
        status="pending",
    )

    service = HistoricalBackfillService()
    result = service.run(session=session, tenant_id=tenant.id)

    assert result.orders_processed == 1
    assert result.gross_sales_total == Decimal("200.00")
    assert result.net_sales_total == Decimal("0.00")
    assert result.pending_sales_total == Decimal("200.00")
    assert result.cancelled_sales_total == Decimal("0.00")
    assert result.verify_accounting_identity()

    metric = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)
    ).scalar_one()
    assert metric.orders_count == 1
    assert metric.gross_sales == Decimal("200.00")
    assert metric.net_sales == Decimal("0.00")
    assert metric.pending_orders_count == 1
    assert metric.pending_sales == Decimal("200.00")
    assert metric.cancelled_orders_count == 0
    assert metric.cancelled_sales == Decimal("0.00")


# ==============================================================================
# TEST 2: Paid Orders
# ==============================================================================
def test_backfill_paid_orders(session: Session) -> None:
    """Verify that paid orders contribute directly to gross_sales and net_sales."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    product = _create_product(session, tenant.id, price=Decimal("150.00"))

    _create_order_with_item(
        session,
        tenant.id,
        customer.id,
        product.id,
        quantity=1,
        unit_price=Decimal("150.00"),
        status="paid",
    )

    service = HistoricalBackfillService()
    result = service.run(session=session, tenant_id=tenant.id)

    assert result.orders_processed == 1
    assert result.gross_sales_total == Decimal("150.00")
    assert result.net_sales_total == Decimal("150.00")
    assert result.pending_sales_total == Decimal("0.00")
    assert result.cancelled_sales_total == Decimal("0.00")
    assert result.verify_accounting_identity()


# ==============================================================================
# TEST 3: Fulfilled Orders (and No Double-Counting with Paid)
# ==============================================================================
def test_backfill_fulfilled_orders_no_double_counting(session: Session) -> None:
    """Verify fulfilled orders are counted in net_sales exactly once alongside paid orders."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    product = _create_product(session, tenant.id, price=Decimal("80.00"))

    # One paid, one fulfilled
    _create_order_with_item(
        session,
        tenant.id,
        customer.id,
        product.id,
        quantity=1,
        unit_price=Decimal("80.00"),
        status="paid",
    )
    _create_order_with_item(
        session,
        tenant.id,
        customer.id,
        product.id,
        quantity=2,
        unit_price=Decimal("80.00"),
        status="fulfilled",
    )

    service = HistoricalBackfillService()
    result = service.run(session=session, tenant_id=tenant.id)

    assert result.orders_processed == 2
    assert result.gross_sales_total == Decimal("240.00")
    assert result.net_sales_total == Decimal("240.00")
    assert result.pending_sales_total == Decimal("0.00")
    assert result.cancelled_sales_total == Decimal("0.00")
    assert result.verify_accounting_identity()


# ==============================================================================
# TEST 4: Cancelled Orders
# ==============================================================================
def test_backfill_cancelled_orders(session: Session) -> None:
    """Verify that cancelled orders populate cancelled_orders_count and cancelled_sales with net_sales = 0."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    product = _create_product(session, tenant.id, price=Decimal("120.00"))

    _create_order_with_item(
        session,
        tenant.id,
        customer.id,
        product.id,
        quantity=1,
        unit_price=Decimal("120.00"),
        status="cancelled",
    )

    service = HistoricalBackfillService()
    result = service.run(session=session, tenant_id=tenant.id)

    assert result.orders_processed == 1
    assert result.gross_sales_total == Decimal("120.00")
    assert result.net_sales_total == Decimal("0.00")
    assert result.pending_sales_total == Decimal("0.00")
    assert result.cancelled_sales_total == Decimal("120.00")
    assert result.verify_accounting_identity()

    metric = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)
    ).scalar_one()
    assert metric.cancelled_orders_count == 1
    assert metric.cancelled_sales == Decimal("120.00")
    assert metric.net_sales == Decimal("0.00")


# ==============================================================================
# TEST 5: Multiple Tenants Isolation
# ==============================================================================
def test_backfill_multiple_tenants_isolation(session: Session) -> None:
    """Verify strict tenant isolation and that single-tenant filtering does not bleed data."""
    tenant_a = _create_tenant(session, name="Tenant A")
    tenant_b = _create_tenant(session, name="Tenant B")

    cust_a = _create_customer(session, tenant_a.id)
    cust_b = _create_customer(session, tenant_b.id)

    prod_a = _create_product(session, tenant_a.id, price=Decimal("100.00"))
    prod_b = _create_product(session, tenant_b.id, price=Decimal("300.00"))

    _create_order_with_item(
        session, tenant_a.id, cust_a.id, prod_a.id, quantity=1, unit_price=Decimal("100.00"), status="paid"
    )
    _create_order_with_item(
        session, tenant_b.id, cust_b.id, prod_b.id, quantity=2, unit_price=Decimal("300.00"), status="paid"
    )

    service = HistoricalBackfillService()

    # Backfill ONLY Tenant A
    result_a = service.run(session=session, tenant_id=tenant_a.id)
    assert result_a.orders_processed == 1
    assert result_a.gross_sales_total == Decimal("100.00")

    # Tenant B should have 0 metrics
    count_b = session.execute(
        select(func.count(DailyTenantMetric.id)).where(DailyTenantMetric.tenant_id == tenant_b.id)
    ).scalar()
    assert count_b == 0

    # Backfill all tenants
    result_all = service.run(session=session)
    assert result_all.orders_processed == 2  # 1 order from A + 1 order from B
    assert result_all.order_items_processed == 2
    assert result_all.gross_sales_total == Decimal("700.00")  # 100 + 600


# ==============================================================================
# TEST 6: Multiple Currencies Segregation
# ==============================================================================
def test_backfill_multiple_currencies_segregation(session: Session) -> None:
    """Verify that multiple currencies on the same date produce separate metric rows without mixing."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod_usd = _create_product(session, tenant.id, price=Decimal("50.00"), currency="USD")
    prod_inr = _create_product(session, tenant.id, price=Decimal("4000.00"), currency="INR")

    fixed_time = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    _create_order_with_item(
        session,
        tenant.id,
        customer.id,
        prod_usd.id,
        quantity=2,
        unit_price=Decimal("50.00"),
        currency="USD",
        status="paid",
        created_at=fixed_time,
    )
    _create_order_with_item(
        session,
        tenant.id,
        customer.id,
        prod_inr.id,
        quantity=1,
        unit_price=Decimal("4000.00"),
        currency="INR",
        status="paid",
        created_at=fixed_time,
    )

    service = HistoricalBackfillService()
    service.run(session=session, tenant_id=tenant.id)

    metrics = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)
    ).scalars().all()

    assert len(metrics) == 2
    by_curr = {m.currency: m for m in metrics}
    assert "USD" in by_curr
    assert "INR" in by_curr

    assert by_curr["USD"].gross_sales == Decimal("100.00")
    assert by_curr["USD"].orders_count == 1
    assert by_curr["INR"].gross_sales == Decimal("4000.00")
    assert by_curr["INR"].orders_count == 1


# ==============================================================================
# TEST 7: Tenant-Local Timezone Date Boundaries
# ==============================================================================
def test_backfill_tenant_local_timezone_date_boundaries(session: Session) -> None:
    """Verify order timestamps are converted to tenant's configured IANA timezone date."""
    # Order at 2026-10-31 23:30:00 UTC
    # In Asia/Kolkata (+05:30), this is 2026-11-01 05:00:00 -> Date: 2026-11-01
    # In America/New_York (-04:00 EDT), this is 2026-10-31 19:30:00 -> Date: 2026-10-31
    boundary_utc = datetime(2026, 10, 31, 23, 30, 0, tzinfo=timezone.utc)

    tenant_kolkata = _create_tenant(session, name="Kolkata Store", timezone_name="Asia/Kolkata")
    tenant_ny = _create_tenant(session, name="NY Store", timezone_name="America/New_York")

    cust_k = _create_customer(session, tenant_kolkata.id)
    cust_ny = _create_customer(session, tenant_ny.id)

    prod_k = _create_product(session, tenant_kolkata.id, price=Decimal("100.00"))
    prod_ny = _create_product(session, tenant_ny.id, price=Decimal("100.00"))

    _create_order_with_item(
        session, tenant_kolkata.id, cust_k.id, prod_k.id, status="paid", created_at=boundary_utc
    )
    _create_order_with_item(
        session, tenant_ny.id, cust_ny.id, prod_ny.id, status="paid", created_at=boundary_utc
    )

    service = HistoricalBackfillService()
    service.run(session=session)

    m_k = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant_kolkata.id)
    ).scalar_one()
    m_ny = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant_ny.id)
    ).scalar_one()

    # Kolkata local date crossed midnight into Nov 1
    assert str(m_k.metric_date) == "2026-11-01"
    # NY local date remained on Oct 31
    assert str(m_ny.metric_date) == "2026-10-31"


# ==============================================================================
# TEST 8: Product-Level Quantities and Sales
# ==============================================================================
def test_backfill_product_level_quantities_and_sales(session: Session) -> None:
    """Verify detailed product metric quantities, sales, and distinct order counts."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("45.00"))

    # Order 1: 3 units paid = $135.00
    _create_order_with_item(
        session, tenant.id, customer.id, prod.id, quantity=3, unit_price=Decimal("45.00"), status="paid"
    )
    # Order 2: 2 units pending = $90.00
    _create_order_with_item(
        session, tenant.id, customer.id, prod.id, quantity=2, unit_price=Decimal("45.00"), status="pending"
    )
    # Order 3: 1 unit cancelled = $45.00
    _create_order_with_item(
        session, tenant.id, customer.id, prod.id, quantity=1, unit_price=Decimal("45.00"), status="cancelled"
    )

    service = HistoricalBackfillService()
    result = service.run(session=session, tenant_id=tenant.id)

    assert result.orders_processed == 3
    assert result.order_items_processed == 3

    p_metric = session.execute(
        select(DailyProductMetric).where(DailyProductMetric.product_id == prod.id)
    ).scalar_one()

    assert p_metric.units_sold_gross == 6
    assert p_metric.units_sold_net == 3
    assert p_metric.pending_units == 2
    assert p_metric.cancelled_units == 1
    assert p_metric.gross_sales == Decimal("270.00")
    assert p_metric.net_sales == Decimal("135.00")
    assert p_metric.pending_sales == Decimal("90.00")
    assert p_metric.cancelled_sales == Decimal("45.00")
    assert p_metric.orders_count == 3

    # Product accounting identity
    assert p_metric.gross_sales == p_metric.net_sales + p_metric.pending_sales + p_metric.cancelled_sales
    assert p_metric.units_sold_gross == p_metric.units_sold_net + p_metric.pending_units + p_metric.cancelled_units


# ==============================================================================
# TEST 9: Accounting Identity Preservation
# ==============================================================================
def test_backfill_accounting_identity_preservation(session: Session) -> None:
    """Verify the core invariant: gross_sales == net_sales + pending_sales + cancelled_sales."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id)

    statuses = [("pending", 100), ("paid", 250), ("fulfilled", 300), ("cancelled", 80)]
    for status, amount in statuses:
        _create_order_with_item(
            session,
            tenant.id,
            customer.id,
            prod.id,
            quantity=1,
            unit_price=Decimal(str(amount)),
            status=status,
        )

    service = HistoricalBackfillService()
    result = service.run(session=session, tenant_id=tenant.id)

    assert result.gross_sales_total == Decimal("730.00")
    assert result.net_sales_total == Decimal("550.00")  # 250 + 300
    assert result.pending_sales_total == Decimal("100.00")
    assert result.cancelled_sales_total == Decimal("80.00")
    assert result.verify_accounting_identity()


# ==============================================================================
# TEST 10: Empty Dataset
# ==============================================================================
def test_backfill_empty_dataset(session: Session) -> None:
    """Verify that backfill completes without error on an empty dataset."""
    tenant = _create_tenant(session)

    service = HistoricalBackfillService()
    result = service.run(session=session, tenant_id=tenant.id)

    assert result.orders_processed == 0
    assert result.order_items_processed == 0
    assert result.tenant_metrics_count == 0
    assert result.product_metrics_count == 0
    assert result.consumer_events_count == 0
    assert result.gross_sales_total == Decimal("0.00")
    assert result.verify_accounting_identity()


# ==============================================================================
# TEST 11: Backfill Rollback on Failure
# ==============================================================================
def test_backfill_rollback_on_failure(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that an unexpected failure triggers a full rollback and leaves tables untouched."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id)

    _create_order_with_item(
        session, tenant.id, customer.id, prod.id, status="paid"
    )

    service = HistoricalBackfillService()

    # Monkeypatch the metric compiler to simulate a mid-flight unhandled failure
    def boom(*args, **kwargs):
        raise RuntimeError("Simulated mid-flight crash!")

    monkeypatch.setattr(service, "_compile_metrics", boom)

    with pytest.raises(RuntimeError, match="Simulated mid-flight crash!"):
        service.run(session=session, tenant_id=tenant.id)

    # Verify tables have 0 rows due to atomic transaction rollback
    count_t = session.execute(select(func.count(DailyTenantMetric.id))).scalar()
    count_p = session.execute(select(func.count(DailyProductMetric.id))).scalar()
    count_e = session.execute(select(func.count(AnalyticsConsumerEvent.event_id))).scalar()

    assert count_t == 0
    assert count_p == 0
    assert count_e == 0


# ==============================================================================
# TEST 12: Safe Rerun Idempotency
# ==============================================================================
def test_backfill_safe_rerun_idempotency(session: Session) -> None:
    """Verify that executing backfill multiple times produces identical results without duplicating rows."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("120.00"))

    _create_order_with_item(
        session, tenant.id, customer.id, prod.id, quantity=2, unit_price=Decimal("120.00"), status="paid"
    )

    service = HistoricalBackfillService()

    # Run 1
    res1 = service.run(session=session, tenant_id=tenant.id)
    count_t1 = session.execute(select(func.count(DailyTenantMetric.id))).scalar()
    count_p1 = session.execute(select(func.count(DailyProductMetric.id))).scalar()
    count_e1 = session.execute(select(func.count(AnalyticsConsumerEvent.event_id))).scalar()

    # Run 2 (Rerun)
    res2 = service.run(session=session, tenant_id=tenant.id)
    count_t2 = session.execute(select(func.count(DailyTenantMetric.id))).scalar()
    count_p2 = session.execute(select(func.count(DailyProductMetric.id))).scalar()
    count_e2 = session.execute(select(func.count(AnalyticsConsumerEvent.event_id))).scalar()

    # Row counts must remain strictly identical
    assert count_t1 == count_t2 == 1
    assert count_p1 == count_p2 == 1
    assert count_e1 == count_e2 == 1

    # Financials must remain identical
    assert res1.gross_sales_total == res2.gross_sales_total == Decimal("240.00")
    assert res1.net_sales_total == res2.net_sales_total == Decimal("240.00")


# ==============================================================================
# TEST 13: Outbox Event Receipt Creation
# ==============================================================================
def test_backfill_outbox_event_receipt_creation(session: Session) -> None:
    """Verify outbox events visible in snapshot are accurately recorded in analytics_consumer_events."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id)

    order, item, event = _create_order_with_item(
        session, tenant.id, customer.id, prod.id, status="paid"
    )

    consumer_name = "test_analytics_worker"
    service = HistoricalBackfillService(consumer_name=consumer_name)
    result = service.run(session=session, tenant_id=tenant.id, consumer_name=consumer_name)

    assert result.consumer_events_count == 1

    receipt = session.execute(
        select(AnalyticsConsumerEvent).where(
            AnalyticsConsumerEvent.consumer_name == consumer_name,
            AnalyticsConsumerEvent.event_id == event.id,
        )
    ).scalar_one()

    assert receipt.tenant_id == tenant.id
    assert receipt.event_type == "order.paid"
    assert receipt.order_id == order.id
    assert receipt.processed_at is not None


# ==============================================================================
# TEST 14: PostgreSQL Live Set-Based Execution
# ==============================================================================
def test_backfill_live_postgresql(postgres_session: Session) -> None:
    """Verify set-based PostgreSQL aggregation, snapshot consistency, and ON CONFLICT handling."""
    tenant = _create_tenant(postgres_session, name="PG Test Store", timezone_name="Europe/London")
    customer = _create_customer(postgres_session, tenant.id)
    prod = _create_product(postgres_session, tenant.id, price=Decimal("75.00"))

    # Create 1 paid and 1 pending order
    _create_order_with_item(
        postgres_session,
        tenant.id,
        customer.id,
        prod.id,
        quantity=2,
        unit_price=Decimal("75.00"),
        status="paid",
    )
    _create_order_with_item(
        postgres_session,
        tenant.id,
        customer.id,
        prod.id,
        quantity=1,
        unit_price=Decimal("75.00"),
        status="pending",
    )

    service = HistoricalBackfillService(consumer_name="pg_test_worker")
    result = service.run(
        session=postgres_session, tenant_id=tenant.id, consumer_name="pg_test_worker"
    )

    assert result.orders_processed == 2
    assert result.order_items_processed == 2
    assert result.gross_sales_total == Decimal("225.00")
    assert result.net_sales_total == Decimal("150.00")
    assert result.pending_sales_total == Decimal("75.00")
    assert result.cancelled_sales_total == Decimal("0.00")
    assert result.consumer_events_count == 2
    assert result.verify_accounting_identity()


# ==============================================================================
# TEST 15: Event Filtering Ignores Unsupported Event Types
# ==============================================================================
def test_backfill_event_filtering_ignores_unsupported_events(session: Session) -> None:
    """Verify that backfill processes supported order events but excludes unsupported domain events."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id)

    # 1. Supported order event
    order, item, event_order = _create_order_with_item(
        session, tenant.id, customer.id, prod.id, status="paid"
    )

    # 2. Unsupported domain event (e.g. customer.registered or product.updated)
    event_unsupported = OutboxEvent(
        tenant_id=tenant.id,
        event_type="customer.registered",
        payload={
            "customer_id": str(customer.id),
            "email": customer.email,
        },
        created_at=order.created_at,
    )
    session.add(event_unsupported)
    session.flush()

    consumer_name = "filtering_test_worker"
    service = HistoricalBackfillService(consumer_name=consumer_name)
    result = service.run(session=session, tenant_id=tenant.id, consumer_name=consumer_name)

    # Only 1 consumer event receipt created (for order.paid)
    assert result.consumer_events_count == 1

    receipts = session.execute(
        select(AnalyticsConsumerEvent).where(AnalyticsConsumerEvent.consumer_name == consumer_name)
    ).scalars().all()

    assert len(receipts) == 1
    assert receipts[0].event_id == event_order.id
    assert receipts[0].event_type == "order.paid"


# ==============================================================================
# TEST 16: Consumer Receipt Schema Enforces Non-Nullable order_id
# ==============================================================================
def test_consumer_receipt_order_id_non_nullable(session: Session) -> None:
    """Verify that analytics_consumer_events strictly requires non-null order_id for data integrity."""
    tenant = _create_tenant(session)

    # Attempt inserting an event receipt without order_id must fail database integrity check
    bad_receipt = AnalyticsConsumerEvent(
        consumer_name="integrity_worker",
        event_id=uuid.uuid4(),
        tenant_id=tenant.id,
        event_type="order.paid",
        order_id=None,  # type: ignore[arg-type]
    )
    session.add(bad_receipt)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ==============================================================================
# TEST 17: PostgreSQL Advisory Lock Acquisition & Release
# ==============================================================================
def test_advisory_lock_coordination_postgresql(postgres_session: Session) -> None:
    """Verify pg_advisory_xact_lock acquires cleanly and is released at transaction completion."""
    conn = postgres_session.connection()
    # Acquire blocking and non-blocking in current transaction
    assert acquire_advisory_lock(conn, wait=True) is True
    assert acquire_advisory_lock(conn, wait=False) is True


# ==============================================================================
# TEST 18: Backfill Advisory Lock Conflict Rejection
# ==============================================================================
def test_backfill_advisory_lock_conflict(postgres_url: str) -> None:
    """Verify that a non-waiting backfill run raises AnalyticsLockConflictError when lock is held."""
    if not is_postgres_available(postgres_url):
        pytest.skip("PostgreSQL not available for advisory lock conflict test.")

    engine1 = create_database_engine(url=postgres_url)
    engine2 = create_database_engine(url=postgres_url)

    # Connection 1 acquires the transaction-level advisory lock
    conn1 = engine1.connect()
    tx1 = conn1.begin()
    conn1.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": AGGRIX_ANALYTICS_LOCK_ID},
    )

    try:
        # Connection 2 attempts backfill with wait_for_lock=False and must raise conflict error
        service = HistoricalBackfillService(consumer_name="conflict_tester")
        with pytest.raises(AnalyticsLockConflictError, match="Cannot acquire AGGRIX analytics aggregation lock"):
            service.run(engine=engine2, wait_for_lock=False)
    finally:
        # Commit transaction 1, which automatically releases the lock
        tx1.rollback()
        conn1.close()
        engine1.dispose()
        engine2.dispose()


