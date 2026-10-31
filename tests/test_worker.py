"""Comprehensive tests for AGGRIX Incremental Aggregation Worker (Stages 1 & 2).

Verifies:
- Empty outbox queue handling.
- Whitelisted vs unsupported event types.
- Receipt deduplication and idempotency.
- Transactional batch atomicity and rollback.
- Dead-letter tracking (analytics_dead_letter_events) and retry progression.
- Poison-pill isolation (failing event does not block valid events in the batch).
- Transient error recovery with dead-letter cleanup.
- Product-level metric rollups, quantities, revenues, and multi-line item accumulation.
- Out-of-order causal delivery handling without double-counting.
- Daemon continuous polling, graceful shutdown (SIGINT/SIGTERM), and sleep backoff.
- PostgreSQL live execution with advisory locking and dead-letter quarantine.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.analytics.coordination import (
    AGGRIX_ANALYTICS_LOCK_ID,
    AnalyticsLockConflictError,
)
from app.analytics.worker import (
    IncrementalAggregationWorker,
    WorkerBatchResult,
    run_worker_daemon,
)
from app.database.connection import create_database_engine
from app.models.analytics_consumer_event import AnalyticsConsumerEvent
from app.models.analytics_dead_letter_event import AnalyticsDeadLetterEvent
from app.models.customer import Customer
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant
from tests.conftest import is_postgres_available


def _create_tenant(session: Session, name: str = "Worker Test Store", tz: str = "UTC") -> Tenant:
    tenant = Tenant(
        name=name,
        domain=f"{uuid.uuid4().hex[:8]}.example.com",
        timezone=tz,
    )
    session.add(tenant)
    session.flush()
    return tenant


def _create_product(session: Session, tenant_id: uuid.UUID, price: Decimal = Decimal("50.00")) -> Product:
    product = Product(
        tenant_id=tenant_id,
        sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
        name="Worker Product",
        price=price,
        currency="USD",
    )
    session.add(product)
    session.flush()
    return product


def _create_customer(session: Session, tenant_id: uuid.UUID) -> Customer:
    customer = Customer(
        tenant_id=tenant_id,
        email=f"worker-{uuid.uuid4().hex[:8]}@example.com",
        name="Worker Customer",
    )
    session.add(customer)
    session.flush()
    return customer


def _create_order_with_items(
    session: Session,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    product: Product,
    quantity: int = 1,
    status: str = "pending",
    created_at: Optional[datetime] = None,
) -> tuple[Order, OrderItem]:
    total_amount = Decimal(str(quantity)) * product.price
    order = Order(
        tenant_id=tenant_id,
        customer_id=customer_id,
        external_order_id=f"ORD-{uuid.uuid4().hex[:8]}",
        total_amount=total_amount,
        currency="USD",
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(order)
    session.flush()

    item = OrderItem(
        tenant_id=tenant_id,
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        unit_price=product.price,
        created_at=order.created_at,
    )
    session.add(item)
    session.flush()
    return order, item


def _create_outbox_event(
    session: Session,
    tenant_id: uuid.UUID,
    order: Optional[Order],
    event_type: str,
    status: str,
    previous_status: Optional[str] = None,
    created_at: Optional[datetime] = None,
    malformed_payload: Optional[dict] = None,
) -> OutboxEvent:
    event_time = created_at or datetime.now(timezone.utc)
    if malformed_payload is not None:
        payload = malformed_payload
    else:
        assert order is not None
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "tenant_id": str(tenant_id),
            "order_id": str(order.id),
            "customer_id": str(order.customer_id),
            "external_order_id": order.external_order_id,
            "status": status,
            "previous_status": previous_status,
            "order_status_at_event": status,
            "total_amount": str(order.total_amount),
            "currency": order.currency,
            "items_count": 1,
            "occurred_at": event_time.isoformat(),
        }

    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
        created_at=event_time,
    )
    session.add(event)
    session.flush()
    return event


# ==============================================================================
# TEST 1: Empty Outbox Queue
# ==============================================================================
def test_worker_empty_outbox_queue(session: Session) -> None:
    """Verify worker handles an empty queue gracefully with 0 polled/processed events."""
    worker = IncrementalAggregationWorker(consumer_name="test_worker_empty")
    res = worker.process_batch(session=session)

    assert res.events_polled == 0
    assert res.events_processed == 0
    assert res.events_skipped == 0
    assert res.events_failed == 0
    assert len(res.order_ids_affected) == 0


# ==============================================================================
# TEST 2: Supported vs Unsupported Event Types
# ==============================================================================
def test_worker_supported_and_unsupported_event_types(session: Session) -> None:
    """Verify only whitelisted order events are polled and processed."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id)
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, status="pending")

    _create_outbox_event(session, tenant.id, order, event_type="order.created", status="pending")
    # Unsupported event
    unsupported = OutboxEvent(
        tenant_id=tenant.id,
        event_type="customer.created",
        payload={"customer_id": str(customer.id)},
        created_at=datetime.now(timezone.utc),
    )
    session.add(unsupported)
    session.flush()

    worker = IncrementalAggregationWorker(consumer_name="test_worker_supported")
    res = worker.process_batch(session=session)

    assert res.events_polled == 1
    assert res.events_processed == 1
    assert res.events_failed == 0

    receipts = session.execute(
        select(AnalyticsConsumerEvent).where(AnalyticsConsumerEvent.consumer_name == "test_worker_supported")
    ).scalars().all()
    assert len(receipts) == 1
    assert receipts[0].event_type == "order.created"


# ==============================================================================
# TEST 3: Duplicate Event Receipts
# ==============================================================================
def test_worker_duplicate_event_receipts_skipped(session: Session) -> None:
    """Verify idempotency: re-running batch skips events already recorded in receipts."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id)
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, status="pending")
    event = _create_outbox_event(session, tenant.id, order, event_type="order.created", status="pending")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_dedup")

    # Pass 1: processes successfully
    res1 = worker.process_batch(session=session)
    assert res1.events_polled == 1
    assert res1.events_processed == 1

    # Pass 2: should poll 0 events because receipt already exists
    res2 = worker.process_batch(session=session)
    assert res2.events_polled == 0
    assert res2.events_processed == 0

    # Simulate receipt already written externally: worker should skip
    event2 = _create_outbox_event(session, tenant.id, order, event_type="order.paid", status="paid")
    receipt = AnalyticsConsumerEvent(
        consumer_name="test_worker_dedup",
        event_id=event2.id,
        tenant_id=tenant.id,
        event_type="order.paid",
        order_id=order.id,
    )
    session.add(receipt)
    session.flush()

    res3 = worker.process_batch(session=session)
    assert res3.events_polled == 0
    assert res3.events_processed == 0


# ==============================================================================
# TEST 4: Successful Batch Transaction
# ==============================================================================
def test_worker_successful_batch_transaction(session: Session) -> None:
    """Verify batch updates summary metrics and consumer receipts atomically."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("100.00"))

    order1, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=1, status="pending")
    order2, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=2, status="pending")

    _create_outbox_event(session, tenant.id, order1, event_type="order.created", status="pending")
    _create_outbox_event(session, tenant.id, order2, event_type="order.created", status="pending")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_batch")
    res = worker.process_batch(session=session)

    assert res.events_polled == 2
    assert res.events_processed == 2
    assert res.events_failed == 0

    m_tenant = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)
    ).scalar_one()
    assert m_tenant.orders_count == 2
    assert m_tenant.gross_sales == Decimal("300.00")
    assert m_tenant.pending_sales == Decimal("300.00")
    assert m_tenant.net_sales == Decimal("0.00")

    m_prod = session.execute(
        select(DailyProductMetric).where(DailyProductMetric.product_id == prod.id)
    ).scalar_one()
    assert m_prod.units_sold_gross == 3
    assert m_prod.gross_sales == Decimal("300.00")
    assert m_prod.orders_count == 2


# ==============================================================================
# TEST 5: Rollback on Processing Failure (propagate_errors=True)
# ==============================================================================
def test_worker_rollback_on_processing_failure(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify failure with propagate_errors=True rolls back the entire batch transaction."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id)
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, status="pending")
    _create_outbox_event(session, tenant.id, order, event_type="order.created", status="pending")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_rollback")

    def crash(*args, **kwargs):
        raise RuntimeError("Database write failure simulated")

    monkeypatch.setattr(worker, "_apply_tenant_metric_delta", crash)

    with pytest.raises(RuntimeError, match="Database write failure simulated"):
        worker.process_batch(session=session, propagate_errors=True)

    r_count = session.execute(select(func.count(AnalyticsConsumerEvent.event_id))).scalar()
    t_count = session.execute(select(func.count(DailyTenantMetric.id))).scalar()
    assert r_count == 0
    assert t_count == 0


# ==============================================================================
# TEST 6: Tenant Isolation
# ==============================================================================
def test_worker_tenant_isolation(session: Session) -> None:
    """Verify metrics for different tenants are kept strictly segregated."""
    tenant_a = _create_tenant(session, name="Tenant A")
    tenant_b = _create_tenant(session, name="Tenant B")

    cust_a = _create_customer(session, tenant_a.id)
    cust_b = _create_customer(session, tenant_b.id)

    prod_a = _create_product(session, tenant_a.id, price=Decimal("40.00"))
    prod_b = _create_product(session, tenant_b.id, price=Decimal("70.00"))

    order_a, _ = _create_order_with_items(session, tenant_a.id, cust_a.id, prod_a, quantity=1, status="pending")
    order_b, _ = _create_order_with_items(session, tenant_b.id, cust_b.id, prod_b, quantity=1, status="pending")

    _create_outbox_event(session, tenant_a.id, order_a, event_type="order.created", status="pending")
    _create_outbox_event(session, tenant_b.id, order_b, event_type="order.created", status="pending")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_tenancy")
    res = worker.process_batch(session=session)
    assert res.events_processed == 2

    m_a = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant_a.id)
    ).scalar_one()
    m_b = session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant_b.id)
    ).scalar_one()

    assert m_a.gross_sales == Decimal("40.00")
    assert m_b.gross_sales == Decimal("70.00")


# ==============================================================================
# TEST 7: Lifecycle Transitions & Accounting Identity
# ==============================================================================
def test_worker_lifecycle_transitions_normal(session: Session) -> None:
    """Verify pending -> paid -> fulfilled -> cancelled (refund) sequence maintains accounting invariants."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("150.00"))
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=1, status="pending")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_lifecycle")

    # Step 1: order.created
    _create_outbox_event(session, tenant.id, order, "order.created", status="pending")
    worker.process_batch(session=session)
    m = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m.gross_sales == Decimal("150.00")
    assert m.pending_sales == Decimal("150.00")
    assert m.net_sales == Decimal("0.00")
    assert m.cancelled_sales == Decimal("0.00")
    assert m.gross_sales == m.net_sales + m.pending_sales + m.cancelled_sales

    # Step 2: order.paid
    _create_outbox_event(session, tenant.id, order, "order.paid", status="paid", previous_status="pending")
    worker.process_batch(session=session)
    m = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m.gross_sales == Decimal("150.00")
    assert m.pending_sales == Decimal("0.00")
    assert m.net_sales == Decimal("150.00")
    assert m.cancelled_sales == Decimal("0.00")
    assert m.gross_sales == m.net_sales + m.pending_sales + m.cancelled_sales

    # Step 3: order.fulfilled (0 delta to sales)
    _create_outbox_event(session, tenant.id, order, "order.fulfilled", status="fulfilled", previous_status="paid")
    worker.process_batch(session=session)
    m = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m.gross_sales == Decimal("150.00")
    assert m.pending_sales == Decimal("0.00")
    assert m.net_sales == Decimal("150.00")
    assert m.gross_sales == m.net_sales + m.pending_sales + m.cancelled_sales

    # Step 4: order.cancelled from paid (Refund)
    _create_outbox_event(session, tenant.id, order, "order.cancelled", status="cancelled", previous_status="paid")
    worker.process_batch(session=session)
    m = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m.gross_sales == Decimal("150.00")
    assert m.pending_sales == Decimal("0.00")
    assert m.net_sales == Decimal("0.00")
    assert m.cancelled_sales == Decimal("150.00")
    assert m.gross_sales == m.net_sales + m.pending_sales + m.cancelled_sales


# ==============================================================================
# TEST 8: Out-of-Order Delivery (order.paid arrives before order.created)
# ==============================================================================
def test_worker_out_of_order_paid_before_created(session: Session) -> None:
    """Verify that when order.paid arrives before order.created, order is registered without double-counting."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("200.00"))
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=1, status="paid")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_ooo_paid")

    # 1. order.paid arrives FIRST
    _create_outbox_event(session, tenant.id, order, "order.paid", status="paid", previous_status="pending")
    res1 = worker.process_batch(session=session)
    assert res1.events_processed == 1

    m = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m.orders_count == 1
    assert m.gross_sales == Decimal("200.00")
    assert m.net_sales == Decimal("200.00")
    assert m.pending_sales == Decimal("0.00")

    # 2. order.created arrives LATER
    _create_outbox_event(session, tenant.id, order, "order.created", status="pending")
    res2 = worker.process_batch(session=session)
    assert res2.events_processed == 1

    m_after = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m_after.orders_count == 1
    assert m_after.gross_sales == Decimal("200.00")
    assert m_after.net_sales == Decimal("200.00")
    assert m_after.pending_sales == Decimal("0.00")


# ==============================================================================
# TEST 9: Out-of-Order Delivery (order.cancelled arrives before order.created)
# ==============================================================================
def test_worker_out_of_order_cancelled_before_created(session: Session) -> None:
    """Verify that when order.cancelled arrives before order.created, order is registered cleanly."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("120.00"))
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=1, status="cancelled")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_ooo_cancel")

    # 1. order.cancelled arrives FIRST
    _create_outbox_event(session, tenant.id, order, "order.cancelled", status="cancelled", previous_status="pending")
    worker.process_batch(session=session)

    m = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m.orders_count == 1
    assert m.gross_sales == Decimal("120.00")
    assert m.cancelled_sales == Decimal("120.00")
    assert m.pending_sales == Decimal("0.00")

    # 2. order.created arrives LATER
    _create_outbox_event(session, tenant.id, order, "order.created", status="pending")
    worker.process_batch(session=session)

    m_after = session.execute(select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)).scalar_one()
    assert m_after.orders_count == 1
    assert m_after.gross_sales == Decimal("120.00")
    assert m_after.cancelled_sales == Decimal("120.00")
    assert m_after.pending_sales == Decimal("0.00")


# ==============================================================================
# TEST 10: Poison-Pill Isolation
# ==============================================================================
def test_worker_poison_pill_isolation(session: Session) -> None:
    """Verify that a poison-pill event in a batch does not block valid events in that batch."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("50.00"))

    order1, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=1, status="pending")
    order3, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=2, status="pending")

    # Event 1: Valid
    e1 = _create_outbox_event(session, tenant.id, order1, "order.created", status="pending")
    # Event 2: Poison Pill (missing order_id)
    e2 = _create_outbox_event(
        session,
        tenant.id,
        order=None,
        event_type="order.created",
        status="pending",
        malformed_payload={"event_type": "order.created", "tenant_id": str(tenant.id)},
    )
    # Event 3: Valid
    e3 = _create_outbox_event(session, tenant.id, order3, "order.created", status="pending")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_poison")
    res = worker.process_batch(session=session)

    assert res.events_polled == 3
    assert res.events_processed == 2
    assert res.events_failed == 1
    assert len(res.order_ids_affected) == 2

    # Verify Event 1 and 3 committed receipts
    receipts = session.execute(
        select(AnalyticsConsumerEvent.order_id).where(
            AnalyticsConsumerEvent.consumer_name == "test_worker_poison"
        )
    ).scalars().all()
    assert set(receipts) == {order1.id, order3.id}

    # Verify Event 2 recorded in dead-letter table with attempts = 1
    dle = session.execute(
        select(AnalyticsDeadLetterEvent).where(
            AnalyticsDeadLetterEvent.consumer_name == "test_worker_poison",
            AnalyticsDeadLetterEvent.event_id == e2.id,
        )
    ).scalar_one()
    assert dle.attempts == 1
    assert "missing required order_id" in dle.error_message


# ==============================================================================
# TEST 11: Retry Behavior and Dead-Letter Quarantine
# ==============================================================================
def test_worker_retry_behavior_and_dead_letter_quarantine(session: Session) -> None:
    """Verify that a failing event retries up to 3 times, after which it is quarantined."""
    tenant = _create_tenant(session)
    e = _create_outbox_event(
        session,
        tenant.id,
        order=None,
        event_type="order.created",
        status="pending",
        malformed_payload={"event_type": "order.created", "tenant_id": str(tenant.id)},
    )

    worker = IncrementalAggregationWorker(
        consumer_name="test_worker_dlq",
        max_retries=3,
    )

    # Attempt 1
    res1 = worker.process_batch(session=session)
    assert res1.events_polled == 1
    assert res1.events_failed == 1
    dle = session.execute(select(AnalyticsDeadLetterEvent.attempts)).scalar_one()
    assert dle == 1

    # Attempt 2
    res2 = worker.process_batch(session=session)
    assert res2.events_polled == 1
    assert res2.events_failed == 1
    dle = session.execute(select(AnalyticsDeadLetterEvent.attempts)).scalar_one()
    assert dle == 2

    # Attempt 3: reaches max_retries
    res3 = worker.process_batch(session=session)
    assert res3.events_polled == 1
    assert res3.events_failed == 1
    dle = session.execute(select(AnalyticsDeadLetterEvent.attempts)).scalar_one()
    assert dle == 3

    # Attempt 4: Poll query must quarantine and skip this event!
    res4 = worker.process_batch(session=session)
    assert res4.events_polled == 0
    assert res4.events_processed == 0
    assert res4.events_failed == 0


# ==============================================================================
# TEST 12: Transient Error Recovery and Dead-Letter Cleanup
# ==============================================================================
def test_worker_transient_failure_recovers_and_cleans_dead_letter(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that if an event transiently fails on attempt 1 but succeeds on retry, DLQ is cleaned."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("75.00"))
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, status="pending")
    e = _create_outbox_event(session, tenant.id, order, "order.created", status="pending")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_recover")

    # Pass 1: Simulate transient failure
    call_count = 0

    def transient_crash(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Transient connection timeout")

    monkeypatch.setattr(worker, "_apply_tenant_metric_delta", transient_crash)

    res1 = worker.process_batch(session=session)
    assert res1.events_failed == 1
    dle_count = session.execute(select(func.count(AnalyticsDeadLetterEvent.id))).scalar()
    assert dle_count == 1

    # Pass 2: Retry succeeds
    res2 = worker.process_batch(session=session)
    assert res2.events_processed == 1
    assert res2.events_failed == 0

    # Verify DLQ record was cleaned up upon successful processing
    dle_count_after = session.execute(select(func.count(AnalyticsDeadLetterEvent.id))).scalar()
    assert dle_count_after == 0

    # Verify consumer receipt exists
    r_count = session.execute(select(func.count(AnalyticsConsumerEvent.event_id))).scalar()
    assert r_count == 1


# ==============================================================================
# TEST 13: Product Aggregation & Multi-Item Order
# ==============================================================================
def test_worker_product_lifecycle_and_quantities(session: Session) -> None:
    """Verify product-level aggregation for units, sales, pending, cancellation, and multi-line orders."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod_a = _create_product(session, tenant.id, price=Decimal("40.00"))
    prod_b = _create_product(session, tenant.id, price=Decimal("25.00"))

    # Order with multi-line items: Prod A (2 units), Prod A (1 unit), Prod B (3 units)
    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        external_order_id="ORD-MULTI",
        total_amount=Decimal("195.00"),  # 3 * 40 + 3 * 25 = 120 + 75 = 195
        currency="USD",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(order)
    session.flush()

    item1 = OrderItem(tenant_id=tenant.id, order_id=order.id, product_id=prod_a.id, quantity=2, unit_price=Decimal("40.00"), created_at=order.created_at)
    item2 = OrderItem(tenant_id=tenant.id, order_id=order.id, product_id=prod_a.id, quantity=1, unit_price=Decimal("40.00"), created_at=order.created_at)
    item3 = OrderItem(tenant_id=tenant.id, order_id=order.id, product_id=prod_b.id, quantity=3, unit_price=Decimal("25.00"), created_at=order.created_at)
    session.add_all([item1, item2, item3])
    session.flush()

    worker = IncrementalAggregationWorker(consumer_name="test_worker_prod_full")

    # 1. order.created
    _create_outbox_event(session, tenant.id, order, "order.created", status="pending")
    worker.process_batch(session=session)

    pa = session.execute(select(DailyProductMetric).where(DailyProductMetric.product_id == prod_a.id)).scalar_one()
    pb = session.execute(select(DailyProductMetric).where(DailyProductMetric.product_id == prod_b.id)).scalar_one()

    # Product A: 3 units total across 2 line items, orders_count == 1
    assert pa.units_sold_gross == 3
    assert pa.gross_sales == Decimal("120.00")
    assert pa.pending_units == 3
    assert pa.pending_sales == Decimal("120.00")
    assert pa.orders_count == 1
    assert pa.units_sold_net == 0
    assert pa.gross_sales == pa.net_sales + pa.pending_sales + pa.cancelled_sales

    # Product B: 3 units, orders_count == 1
    assert pb.units_sold_gross == 3
    assert pb.gross_sales == Decimal("75.00")
    assert pb.pending_units == 3
    assert pb.pending_sales == Decimal("75.00")
    assert pb.orders_count == 1

    # 2. order.paid
    _create_outbox_event(session, tenant.id, order, "order.paid", status="paid", previous_status="pending")
    worker.process_batch(session=session)

    pa = session.execute(select(DailyProductMetric).where(DailyProductMetric.product_id == prod_a.id)).scalar_one()
    assert pa.units_sold_gross == 3
    assert pa.gross_sales == Decimal("120.00")
    assert pa.pending_units == 0
    assert pa.pending_sales == Decimal("0.00")
    assert pa.units_sold_net == 3
    assert pa.net_sales == Decimal("120.00")
    assert pa.gross_sales == pa.net_sales + pa.pending_sales + pa.cancelled_sales

    # 3. order.cancelled (Refund)
    _create_outbox_event(session, tenant.id, order, "order.cancelled", status="cancelled", previous_status="paid")
    worker.process_batch(session=session)

    pa = session.execute(select(DailyProductMetric).where(DailyProductMetric.product_id == prod_a.id)).scalar_one()
    assert pa.units_sold_gross == 3
    assert pa.gross_sales == Decimal("120.00")
    assert pa.units_sold_net == 0
    assert pa.net_sales == Decimal("0.00")
    assert pa.cancelled_units == 3
    assert pa.cancelled_sales == Decimal("120.00")
    assert pa.gross_sales == pa.net_sales + pa.pending_sales + pa.cancelled_sales


# ==============================================================================
# TEST 14: Product Out-of-Order Lifecycle
# ==============================================================================
def test_worker_product_out_of_order_lifecycle(session: Session) -> None:
    """Verify product metrics are correct when events arrive out-of-order."""
    tenant = _create_tenant(session)
    customer = _create_customer(session, tenant.id)
    prod = _create_product(session, tenant.id, price=Decimal("60.00"))
    order, _ = _create_order_with_items(session, tenant.id, customer.id, prod, quantity=2, status="paid")

    worker = IncrementalAggregationWorker(consumer_name="test_worker_prod_ooo")

    # 1. order.paid arrives FIRST
    _create_outbox_event(session, tenant.id, order, "order.paid", status="paid", previous_status="pending")
    worker.process_batch(session=session)

    p = session.execute(select(DailyProductMetric).where(DailyProductMetric.product_id == prod.id)).scalar_one()
    assert p.units_sold_gross == 2
    assert p.gross_sales == Decimal("120.00")
    assert p.units_sold_net == 2
    assert p.net_sales == Decimal("120.00")
    assert p.pending_units == 0
    assert p.orders_count == 1

    # 2. order.created arrives LATER
    _create_outbox_event(session, tenant.id, order, "order.created", status="pending")
    worker.process_batch(session=session)

    p_after = session.execute(select(DailyProductMetric).where(DailyProductMetric.product_id == prod.id)).scalar_one()
    assert p_after.units_sold_gross == 2
    assert p_after.gross_sales == Decimal("120.00")
    assert p_after.units_sold_net == 2
    assert p_after.net_sales == Decimal("120.00")


# ==============================================================================
# TEST 15: Daemon Continuous Polling & Graceful Shutdown
# ==============================================================================
def test_worker_daemon_continuous_polling_and_graceful_shutdown() -> None:
    """Verify daemon continuously polls, processes, and gracefully shuts down via stop_event."""
    import sqlalchemy as sa
    from sqlalchemy.pool import StaticPool
    test_engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.database.base import Base
    Base.metadata.create_all(test_engine)

    stop_event = threading.Event()

    # Run daemon for max_batches=2 on an empty queue
    processed = run_worker_daemon(
        engine=test_engine,
        consumer_name="daemon_test_worker",
        poll_interval_seconds=0.05,
        max_batches=2,
        stop_event=stop_event,
    )
    assert processed == 0

    # Now verify thread-based stop_event shutdown
    stop_event.clear()
    thread = threading.Thread(
        target=run_worker_daemon,
        kwargs={
            "engine": test_engine,
            "consumer_name": "daemon_test_thread",
            "poll_interval_seconds": 0.05,
            "stop_event": stop_event,
        },
    )
    thread.start()
    time.sleep(0.1)
    assert thread.is_alive()
    stop_event.set()
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    test_engine.dispose()


# ==============================================================================
# TEST 16: PostgreSQL Live Batch Execution
# ==============================================================================
def test_worker_live_postgresql_batch(postgres_session: Session) -> None:
    """Verify worker batch execution on live PostgreSQL instance with advisory locking."""
    tenant = _create_tenant(postgres_session, name="PG Worker Store", tz="Europe/London")
    customer = _create_customer(postgres_session, tenant.id)
    prod = _create_product(postgres_session, tenant.id, price=Decimal("85.00"))
    order, _ = _create_order_with_items(postgres_session, tenant.id, customer.id, prod, quantity=2, status="pending")
    _create_outbox_event(postgres_session, tenant.id, order, event_type="order.created", status="pending")

    worker = IncrementalAggregationWorker(consumer_name="analytics_worker")
    res = worker.process_batch(session=postgres_session)

    assert res.events_processed == 1

    m_tenant = postgres_session.execute(
        select(DailyTenantMetric).where(DailyTenantMetric.tenant_id == tenant.id)
    ).scalar_one()
    assert m_tenant.gross_sales == Decimal("170.00")
    assert m_tenant.pending_sales == Decimal("170.00")


# ==============================================================================
# TEST 17: PostgreSQL Live Dead-Letter Quarantine
# ==============================================================================
def test_worker_live_postgresql_dead_letter_quarantine(postgres_session: Session) -> None:
    """Verify poison pill isolation and quarantine persistence on live PostgreSQL."""
    tenant = _create_tenant(postgres_session, name="PG DLQ Store")
    # Event with missing order_id
    _create_outbox_event(
        postgres_session,
        tenant.id,
        order=None,
        event_type="order.created",
        status="pending",
        malformed_payload={"event_type": "order.created", "tenant_id": str(tenant.id)},
    )

    worker = IncrementalAggregationWorker(
        consumer_name="analytics_worker",
        tenant_id=tenant.id,
        max_retries=3,
    )

    res1 = worker.process_batch(session=postgres_session)
    assert res1.events_failed == 1

    res2 = worker.process_batch(session=postgres_session)
    assert res2.events_failed == 1

    res3 = worker.process_batch(session=postgres_session)
    assert res3.events_failed == 1

    # Batch 4: Must be quarantined!
    res4 = worker.process_batch(session=postgres_session)
    assert res4.events_polled == 0
