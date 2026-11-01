"""
Unit and Integration Tests for AGGRIX Dead Letter Queue (DLQ) Inspection and Replay.

Verifies:
1. DLQ record querying with tenant and quarantine filtering.
2. Successful event replay through IncrementalAggregationWorker.
3. Atomic cleanup of DLQ records upon successful replay.
4. Idempotency guarantees (no double-counting on re-replay).
5. Error handling and DLQ update when replay fails.
6. Attempt counter reset for daemon worker retry.
7. DLQ CLI commands (inspect, replay, reset).
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.analytics.worker import IncrementalAggregationWorker
from app.cli.dlq import main as dlq_main
from app.database.base import Base
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


# ==============================================================================
# Isolated SQLite Test Fixtures
# ==============================================================================

@pytest.fixture
def dlq_engine() -> Generator[sa.Engine, None, None]:
    """Isolated, thread-safe in-memory SQLite engine for DLQ testing."""
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa.event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def dlq_session(dlq_engine: sa.Engine) -> Generator[Session, None, None]:
    """Yields a database session against isolated engine."""
    session_factory = sessionmaker(bind=dlq_engine, expire_on_commit=False)
    sess = session_factory()
    yield sess
    sess.close()


@pytest.fixture
def sample_tenant(dlq_session: Session) -> Tenant:
    """Create a sample tenant store."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name="DLQ Test Store",
        domain="dlq-test.myshopify.com",
        timezone="UTC",
    )
    dlq_session.add(tenant)
    dlq_session.commit()
    return tenant


@pytest.fixture
def sample_customer(dlq_session: Session, sample_tenant: Tenant) -> Customer:
    """Create a sample tenant customer."""
    customer = Customer(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        email="customer@example.com",
        name="Jane Doe",
    )
    dlq_session.add(customer)
    dlq_session.commit()
    return customer


@pytest.fixture
def sample_product(dlq_session: Session, sample_tenant: Tenant) -> Product:
    """Create a sample catalog product."""
    product = Product(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        name="Test Widget",
        sku="WIDGET-01",
        price=Decimal("50.00"),
    )
    dlq_session.add(product)
    dlq_session.commit()
    return product


# ==============================================================================
# Unit & Integration Tests: DLQ Inspection and Replay
# ==============================================================================

class TestDLQReplayAndWorker:
    """Tests for IncrementalAggregationWorker DLQ capabilities."""

    def test_get_dead_letter_events_empty_and_populated(
        self, dlq_engine: sa.Engine, dlq_session: Session, sample_tenant: Tenant
    ):
        worker = IncrementalAggregationWorker(engine=dlq_engine, max_retries=3)

        with dlq_engine.connect() as conn:
            # 1. Empty initially
            records = worker.get_dead_letter_events(conn)
            assert len(records) == 0

        # 2. Add transient failure (attempts=1 < 3)
        e_id_transient = uuid.uuid4()
        dlq_session.add(
            OutboxEvent(
                id=e_id_transient,
                tenant_id=sample_tenant.id,
                event_type="order.created",
                payload={"order_id": str(uuid.uuid4())},
            )
        )
        dlq_session.flush()

        dlq_session.add(
            AnalyticsDeadLetterEvent(
                id=uuid.uuid4(),
                consumer_name="analytics_worker",
                event_id=e_id_transient,
                tenant_id=sample_tenant.id,
                event_type="order.created",
                error_message="Transient network glitch",
                attempts=1,
            )
        )

        # 3. Add quarantined failure (attempts=3)
        e_id_quarantined = uuid.uuid4()
        dlq_session.add(
            OutboxEvent(
                id=e_id_quarantined,
                tenant_id=sample_tenant.id,
                event_type="order.created",
                payload={"order_id": str(uuid.uuid4())},
            )
        )
        dlq_session.flush()

        dlq_session.add(
            AnalyticsDeadLetterEvent(
                id=uuid.uuid4(),
                consumer_name="analytics_worker",
                event_id=e_id_quarantined,
                tenant_id=sample_tenant.id,
                event_type="order.created",
                error_message="Permanent schema error",
                attempts=3,
            )
        )
        dlq_session.commit()

        with dlq_engine.connect() as conn:
            # Quarantined only (default): should return 1
            quarantined = worker.get_dead_letter_events(conn, quarantined_only=True)
            assert len(quarantined) == 1
            assert quarantined[0]["event_id"] == e_id_quarantined

            # All (including transient): should return 2
            all_records = worker.get_dead_letter_events(conn, quarantined_only=False)
            assert len(all_records) == 2

    def test_successful_dead_letter_replay(
        self,
        dlq_engine: sa.Engine,
        dlq_session: Session,
        sample_tenant: Tenant,
        sample_customer: Customer,
        sample_product: Product,
    ):
        worker = IncrementalAggregationWorker(engine=dlq_engine)

        # Create order, item, and outbox event
        order_id = uuid.uuid4()
        now_dt = datetime.now(timezone.utc)
        order = Order(
            id=order_id,
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            external_order_id="ORD-DLQ-100",
            currency="USD",
            total_amount=Decimal("100.00"),
            status="pending",
            created_at=now_dt,
        )
        dlq_session.add(order)
        item = OrderItem(
            id=uuid.uuid4(),
            tenant_id=sample_tenant.id,
            order_id=order_id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal("50.00"),
        )
        dlq_session.add(item)

        event_id = uuid.uuid4()
        outbox = OutboxEvent(
            id=event_id,
            tenant_id=sample_tenant.id,
            event_type="order.created",
            payload={"order_id": str(order_id)},
            created_at=now_dt,
        )
        dlq_session.add(outbox)
        dlq_session.flush()

        # Quarantined in DLQ with 3 failed attempts
        dlq_record = AnalyticsDeadLetterEvent(
            id=uuid.uuid4(),
            consumer_name="analytics_worker",
            event_id=event_id,
            tenant_id=sample_tenant.id,
            event_type="order.created",
            order_id=order_id,
            error_message="Simulated past failure",
            attempts=3,
        )
        dlq_session.add(dlq_record)
        dlq_session.commit()

        # Replay the dead-letter event
        with dlq_engine.connect() as conn:
            with conn.begin():
                success = worker.replay_dead_letter_event(conn, event_id)
                assert success is True

        # Verify DLQ record was deleted
        dlq_check = dlq_session.execute(
            sa.select(AnalyticsDeadLetterEvent).where(AnalyticsDeadLetterEvent.event_id == event_id)
        ).scalar_one_or_none()
        assert dlq_check is None

        # Verify consumer receipt was written
        receipt = dlq_session.execute(
            sa.select(AnalyticsConsumerEvent).where(AnalyticsConsumerEvent.event_id == event_id)
        ).scalar_one_or_none()
        assert receipt is not None
        assert receipt.order_id == order_id

        # Verify tenant metrics updated
        metric_date = now_dt.date()
        tenant_metric = dlq_session.execute(
            sa.select(DailyTenantMetric).where(
                DailyTenantMetric.tenant_id == sample_tenant.id,
                DailyTenantMetric.metric_date == metric_date,
            )
        ).scalar_one_or_none()
        assert tenant_metric is not None
        assert tenant_metric.orders_count == 1
        assert tenant_metric.gross_sales == Decimal("100.00")
        assert tenant_metric.pending_orders_count == 1
        assert tenant_metric.pending_sales == Decimal("100.00")

        # Verify product metrics updated
        prod_metric = dlq_session.execute(
            sa.select(DailyProductMetric).where(
                DailyProductMetric.tenant_id == sample_tenant.id,
                DailyProductMetric.product_id == sample_product.id,
                DailyProductMetric.metric_date == metric_date,
            )
        ).scalar_one_or_none()
        assert prod_metric is not None
        assert prod_metric.units_sold_gross == 2
        assert prod_metric.pending_units == 2
        assert prod_metric.gross_sales == Decimal("100.00")

    def test_replay_idempotency_does_not_double_count(
        self,
        dlq_engine: sa.Engine,
        dlq_session: Session,
        sample_tenant: Tenant,
        sample_customer: Customer,
        sample_product: Product,
    ):
        worker = IncrementalAggregationWorker(engine=dlq_engine)

        order_id = uuid.uuid4()
        now_dt = datetime.now(timezone.utc)
        order = Order(
            id=order_id,
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            external_order_id="ORD-IDEMP-01",
            currency="USD",
            total_amount=Decimal("50.00"),
            status="pending",
            created_at=now_dt,
        )
        dlq_session.add(order)
        item = OrderItem(
            id=uuid.uuid4(),
            tenant_id=sample_tenant.id,
            order_id=order_id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal("50.00"),
        )
        dlq_session.add(item)

        event_id = uuid.uuid4()
        outbox = OutboxEvent(
            id=event_id,
            tenant_id=sample_tenant.id,
            event_type="order.created",
            payload={"order_id": str(order_id)},
            created_at=now_dt,
        )
        dlq_session.add(outbox)
        dlq_session.commit()

        # First replay
        with dlq_engine.connect() as conn:
            with conn.begin():
                res1 = worker.replay_dead_letter_event(conn, event_id)
                assert res1 is True

        # Second replay (should be skipped via receipt check)
        with dlq_engine.connect() as conn:
            with conn.begin():
                res2 = worker.replay_dead_letter_event(conn, event_id)
                assert res2 is False

        # Confirm orders_count is still 1, NOT 2
        metric = dlq_session.execute(
            sa.select(DailyTenantMetric).where(
                DailyTenantMetric.tenant_id == sample_tenant.id,
                DailyTenantMetric.metric_date == now_dt.date(),
            )
        ).scalar_one()
        assert metric.orders_count == 1
        assert metric.gross_sales == Decimal("50.00")

    def test_failed_replay_updates_dead_letter_record(
        self, dlq_engine: sa.Engine, dlq_session: Session, sample_tenant: Tenant
    ):
        worker = IncrementalAggregationWorker(engine=dlq_engine)

        # Create outbox event with missing order_id
        event_id = uuid.uuid4()
        outbox = OutboxEvent(
            id=event_id,
            tenant_id=sample_tenant.id,
            event_type="order.created",
            payload={},  # Missing order_id
        )
        dlq_session.add(outbox)
        dlq_session.flush()

        dlq_session.add(
            AnalyticsDeadLetterEvent(
                id=uuid.uuid4(),
                consumer_name="analytics_worker",
                event_id=event_id,
                tenant_id=sample_tenant.id,
                event_type="order.created",
                error_message="Initial failure",
                attempts=3,
            )
        )
        dlq_session.commit()

        with dlq_engine.connect() as conn:
            with conn.begin():
                with pytest.raises(ValueError, match="missing required order_id"):
                    worker.replay_dead_letter_event(conn, event_id)

        # Verify DLQ attempts incremented to 4 and error message updated
        dlq = dlq_session.execute(
            sa.select(AnalyticsDeadLetterEvent).where(AnalyticsDeadLetterEvent.event_id == event_id)
        ).scalar_one()
        assert dlq.attempts == 4
        assert "missing required order_id" in dlq.error_message

    def test_reset_dead_letter_attempts(
        self, dlq_engine: sa.Engine, dlq_session: Session, sample_tenant: Tenant
    ):
        worker = IncrementalAggregationWorker(engine=dlq_engine)

        e1 = uuid.uuid4()
        e2 = uuid.uuid4()
        for e in [e1, e2]:
            dlq_session.add(
                OutboxEvent(
                    id=e,
                    tenant_id=sample_tenant.id,
                    event_type="order.created",
                    payload={},
                )
            )
            dlq_session.flush()
            dlq_session.add(
                AnalyticsDeadLetterEvent(
                    id=uuid.uuid4(),
                    consumer_name="analytics_worker",
                    event_id=e,
                    tenant_id=sample_tenant.id,
                    event_type="order.created",
                    error_message="Failure",
                    attempts=3,
                )
            )
        dlq_session.commit()

        # Reset single event
        with dlq_engine.connect() as conn:
            with conn.begin():
                count = worker.reset_dead_letter_attempts(conn, event_ids=[e1])
                assert count == 1

        d1 = dlq_session.execute(
            sa.select(AnalyticsDeadLetterEvent).where(AnalyticsDeadLetterEvent.event_id == e1)
        ).scalar_one()
        d2 = dlq_session.execute(
            sa.select(AnalyticsDeadLetterEvent).where(AnalyticsDeadLetterEvent.event_id == e2)
        ).scalar_one()
        assert d1.attempts == 0
        assert d2.attempts == 3

        # Reset all events
        with dlq_engine.connect() as conn:
            with conn.begin():
                count_all = worker.reset_dead_letter_attempts(conn)
                assert count_all >= 1

        dlq_session.expire_all()
        d2_reset = dlq_session.execute(
            sa.select(AnalyticsDeadLetterEvent).where(AnalyticsDeadLetterEvent.event_id == e2)
        ).scalar_one()
        assert d2_reset.attempts == 0


# ==============================================================================
# CLI Command Tests: app.cli.dlq
# ==============================================================================

class TestDLQCLI:
    """Tests for DLQ CLI inspect, replay, and reset subcommands."""

    def test_cli_inspect_empty(self, dlq_engine: sa.Engine):
        out = io.StringIO()
        code = dlq_main(argv=["inspect"], engine=dlq_engine, out=out)
        assert code == 0
        assert "No quarantined dead-letter events found" in out.getvalue()

    def test_cli_inspect_populated(self, dlq_engine: sa.Engine, dlq_session: Session, sample_tenant: Tenant):
        eid = uuid.uuid4()
        dlq_session.add(
            OutboxEvent(id=eid, tenant_id=sample_tenant.id, event_type="order.paid", payload={})
        )
        dlq_session.flush()

        dlq_session.add(
            AnalyticsDeadLetterEvent(
                id=uuid.uuid4(),
                consumer_name="analytics_worker",
                event_id=eid,
                tenant_id=sample_tenant.id,
                event_type="order.paid",
                error_message="Timeout on third party payment webhook",
                attempts=3,
            )
        )
        dlq_session.commit()

        out = io.StringIO()
        code = dlq_main(argv=["inspect"], engine=dlq_engine, out=out)
        assert code == 0
        assert str(eid) in out.getvalue()
        assert "order.paid" in out.getvalue()
        assert "Timeout on third party payment" in out.getvalue()

    def test_cli_replay_single_event(
        self,
        dlq_engine: sa.Engine,
        dlq_session: Session,
        sample_tenant: Tenant,
        sample_customer: Customer,
        sample_product: Product,
    ):
        order_id = uuid.uuid4()
        now_dt = datetime.now(timezone.utc)
        order = Order(
            id=order_id,
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            external_order_id="ORD-CLI-01",
            currency="USD",
            total_amount=Decimal("75.00"),
            status="pending",
            created_at=now_dt,
        )
        dlq_session.add(order)
        item = OrderItem(
            id=uuid.uuid4(),
            tenant_id=sample_tenant.id,
            order_id=order_id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal("75.00"),
        )
        dlq_session.add(item)

        event_id = uuid.uuid4()
        outbox = OutboxEvent(
            id=event_id,
            tenant_id=sample_tenant.id,
            event_type="order.created",
            payload={"order_id": str(order_id)},
            created_at=now_dt,
        )
        dlq_session.add(outbox)
        dlq_session.flush()

        dlq_session.add(
            AnalyticsDeadLetterEvent(
                id=uuid.uuid4(),
                consumer_name="analytics_worker",
                event_id=event_id,
                tenant_id=sample_tenant.id,
                event_type="order.created",
                error_message="Old error",
                attempts=3,
            )
        )
        dlq_session.commit()

        out = io.StringIO()
        err = io.StringIO()
        code = dlq_main(argv=["replay", "--event-id", str(event_id)], engine=dlq_engine, out=out, err=err)
        assert code == 0
        assert f"SUCCESS: Event {event_id} replayed successfully" in out.getvalue()

    def test_cli_reset_attempts(self, dlq_engine: sa.Engine, dlq_session: Session, sample_tenant: Tenant):
        eid = uuid.uuid4()
        dlq_session.add(
            OutboxEvent(id=eid, tenant_id=sample_tenant.id, event_type="order.paid", payload={})
        )
        dlq_session.flush()

        dlq_session.add(
            AnalyticsDeadLetterEvent(
                id=uuid.uuid4(),
                consumer_name="analytics_worker",
                event_id=eid,
                tenant_id=sample_tenant.id,
                event_type="order.paid",
                error_message="Some error",
                attempts=3,
            )
        )
        dlq_session.commit()

        out = io.StringIO()
        err = io.StringIO()
        code = dlq_main(argv=["reset", "--event-id", str(eid)], engine=dlq_engine, out=out, err=err)
        assert code == 0
        assert "Reset attempt counters for 1 event(s)" in out.getvalue()

    def test_cli_replay_all_quarantined_events(
        self,
        dlq_engine: sa.Engine,
        dlq_session: Session,
        sample_tenant: Tenant,
        sample_customer: Customer,
        sample_product: Product,
    ):
        order_id = uuid.uuid4()
        now_dt = datetime.now(timezone.utc)
        order = Order(
            id=order_id,
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            external_order_id="ORD-CLI-ALL-01",
            currency="USD",
            total_amount=Decimal("120.00"),
            status="pending",
            created_at=now_dt,
        )
        dlq_session.add(order)
        item = OrderItem(
            id=uuid.uuid4(),
            tenant_id=sample_tenant.id,
            order_id=order_id,
            product_id=sample_product.id,
            quantity=2,
            unit_price=Decimal("60.00"),
        )
        dlq_session.add(item)

        event_id = uuid.uuid4()
        outbox = OutboxEvent(
            id=event_id,
            tenant_id=sample_tenant.id,
            event_type="order.created",
            payload={"order_id": str(order_id)},
            created_at=now_dt,
        )
        dlq_session.add(outbox)
        dlq_session.flush()

        dlq_session.add(
            AnalyticsDeadLetterEvent(
                id=uuid.uuid4(),
                consumer_name="analytics_worker",
                event_id=event_id,
                tenant_id=sample_tenant.id,
                event_type="order.created",
                error_message="Past failure",
                attempts=3,
            )
        )
        dlq_session.commit()

        out = io.StringIO()
        err = io.StringIO()
        code = dlq_main(argv=["replay", "--all"], engine=dlq_engine, out=out, err=err)
        assert code == 0
        assert "Replay Batch Completed: 1 succeeded, 0 failed." in out.getvalue()
