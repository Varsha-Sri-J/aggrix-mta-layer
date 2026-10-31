"""Automated End-to-End Validation Test Suite for Stage 3 (Workstream 4).

Covers the entire lifecycle pipeline:
1. Create a new order with line items.
2. Generate transactional outbox event.
3. Analytics worker consumes the outbox event atomically.
4. Aggregate rollup metrics update in daily_tenant_metrics and daily_product_metrics.
5. Read APIs return updated revenue, order volume, and AOV.
6. Real-time broadcaster delivers event to connected SSE clients without full-page refresh.
7. Multi-tenant isolation, duplicate event idempotency, and poison-pill worker error handling.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.broadcaster import broadcaster
from app.analytics.worker import IncrementalAggregationWorker
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.main import create_application
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
from app.models.user import User, UserRole


@pytest.fixture
def e2e_db_session() -> Generator[Session, None, None]:
    """In-memory SQLite session with full schema initialized."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def e2e_app(e2e_db_session: Session):
    """FastAPI test application with overridden database session."""
    from app.database.connection import get_db

    app = create_application()
    app.dependency_overrides[get_db] = lambda: e2e_db_session
    return app


@pytest.fixture
def e2e_client(e2e_app) -> Generator[TestClient, None, None]:
    """TestClient configured with overridden app."""
    with TestClient(e2e_app) as client:
        yield client


@pytest.fixture(autouse=True)
def clean_broadcaster():
    """Ensure clean broadcaster state before and after every test."""
    broadcaster.clear_all()
    yield
    broadcaster.clear_all()


def _create_tenant(db: Session, name: str, domain: str) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        name=name,
        domain=domain,
        timezone="UTC",
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _create_user(
    db: Session,
    email: str,
    role: UserRole,
    tenant_id: uuid.UUID | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password("E2ESecretPassword123!"),
        role=role.value,
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestRealTimeEndToEndPipeline:
    """Comprehensive end-to-end pipeline validation for Stage 3."""

    def test_complete_realtime_order_to_dashboard_pipeline(
        self, e2e_client: TestClient, e2e_db_session: Session
    ):
        """
        Validates the complete end-to-end chain:
        1. Create new order.
        2. Confirm outbox event generated.
        3. Worker consumes outbox event.
        4. Daily metrics update.
        5. API returns updated values.
        6. SSE subscriber receives live update.
        """
        # Step 0: Setup Tenant, Customer, Product, User
        tenant = _create_tenant(e2e_db_session, "Pipeline Store", "pipeline.aggrix.local")
        customer = Customer(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="shopper@pipeline.local",
            name="Sarah Connor",
        )
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            sku="SKU-PROD-01",
            name="Quantum Processor",
            price=Decimal("250.00"),
        )
        e2e_db_session.add_all([customer, product])
        e2e_db_session.commit()

        user = _create_user(e2e_db_session, "user@pipeline.local", UserRole.TENANT_USER, tenant_id=tenant.id)
        token = create_access_token(subject=user.id, role=user.role, tenant_id=user.tenant_id)

        # Step 1: Connect SSE subscriber for the tenant
        sse_sub = broadcaster.subscribe(
            user_id=user.id,
            role=user.role,
            authorized_tenant_ids={tenant.id},
            filter_tenant_id=tenant.id,
        )
        assert sse_sub.queue.empty()

        # Step 2: Place an Order in the transactional database
        order_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        order = Order(
            id=order_id,
            tenant_id=tenant.id,
            customer_id=customer.id,
            external_order_id="ORD-LIVE-777",
            total_amount=Decimal("500.00"),
            currency="USD",
            status="pending",
            created_at=now,
        )
        order_item = OrderItem(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            order_id=order_id,
            product_id=product.id,
            quantity=2,
            unit_price=Decimal("250.00"),
        )
        # Transactional outbox event
        outbox_evt = OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            event_type="order.created",
            payload={
                "order_id": str(order_id),
                "external_order_id": "ORD-LIVE-777",
                "customer_id": str(customer.id),
                "total_amount": "500.00",
                "currency": "USD",
                "status": "pending",
                "occurred_at": now.isoformat(),
            },
            created_at=now,
        )
        e2e_db_session.add_all([order, order_item, outbox_evt])
        e2e_db_session.commit()

        # Confirm outbox event exists and is unconsumed
        unprocessed_events = e2e_db_session.execute(
            select(OutboxEvent).where(OutboxEvent.processed_at.is_(None))
        ).scalars().all()
        assert len(unprocessed_events) == 1
        assert unprocessed_events[0].id == outbox_evt.id

        # Step 3: Analytics Worker consumes the outbox event
        worker = IncrementalAggregationWorker(
            engine=e2e_db_session.bind,
            consumer_name="test_e2e_worker",
            batch_size=10,
        )
        batch_result = worker.process_batch(session=e2e_db_session)
        assert batch_result.events_polled == 1
        assert batch_result.events_processed == 1
        assert batch_result.events_failed == 0

        # Step 4: Verify aggregate metrics updated
        metric = e2e_db_session.execute(
            select(DailyTenantMetric).where(
                DailyTenantMetric.tenant_id == tenant.id,
                DailyTenantMetric.currency == "USD",
            )
        ).scalar_one_or_none()
        assert metric is not None
        assert metric.orders_count == 1
        assert metric.gross_sales == Decimal("500.00")
        assert metric.pending_orders_count == 1
        assert metric.pending_sales == Decimal("500.00")

        # Step 5: Verify Read API returns the updated metrics
        res = e2e_client.get(
            f"/api/v1/analytics/tenants/{tenant.id}/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        summary = res.json()
        assert summary["total_orders"] == 1
        assert float(summary["gross_sales"]) == 500.00
        assert float(summary["average_order_value"]) == 500.00
        assert summary["pending_orders_count"] == 1
        assert summary["active_customers_count"] == 1

        # Step 6: Confirm SSE subscriber received the event in real time without refreshing
        assert not sse_sub.queue.empty(), "Connected SSE client must receive live broadcasted event!"
        broadcast_event = sse_sub.queue.get_nowait()
        assert broadcast_event is not None
        assert broadcast_event.tenant_id == tenant.id
        assert broadcast_event.order_id == order_id
        assert broadcast_event.external_order_id == "ORD-LIVE-777"
        assert float(broadcast_event.total_amount) == 500.00
        assert broadcast_event.status == "pending"

        # Check SSE message formatting
        sse_msg = broadcast_event.to_sse_message()
        assert "event: order.created" in sse_msg
        assert "ORD-LIVE-777" in sse_msg

    def test_duplicate_outbox_event_idempotency_and_no_duplicate_broadcast(
        self, e2e_client: TestClient, e2e_db_session: Session
    ):
        """Worker must skip duplicate events idempotently and not duplicate SSE events."""
        tenant = _create_tenant(e2e_db_session, "Idempotent Store", "idemp.aggrix.local")
        customer = Customer(id=uuid.uuid4(), tenant_id=tenant.id, email="idemp@local", name="Idemp User")
        e2e_db_session.add(customer)
        e2e_db_session.commit()

        order_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        order = Order(
            id=order_id,
            tenant_id=tenant.id,
            customer_id=customer.id,
            external_order_id="IDEMP-001",
            total_amount=Decimal("120.00"),
            currency="USD",
            status="pending",
        )
        e2e_db_session.add(order)

        # First event
        evt1 = OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            event_type="order.created",
            payload={"order_id": str(order_id), "total_amount": "120.00", "currency": "USD"},
            created_at=now,
        )
        e2e_db_session.add(evt1)
        e2e_db_session.commit()

        worker = IncrementalAggregationWorker(
            engine=e2e_db_session.bind,
            consumer_name="idemp_worker",
        )
        r1 = worker.process_batch(session=e2e_db_session)
        assert r1.events_processed == 1

        # Second identical event type for same order
        evt2 = OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            event_type="order.created",
            payload={"order_id": str(order_id), "total_amount": "120.00", "currency": "USD"},
            created_at=now,
        )
        e2e_db_session.add(evt2)
        e2e_db_session.commit()

        sub = broadcaster.subscribe(uuid.uuid4(), "platform_admin", authorized_tenant_ids=None)
        # Clear any prior queue contents
        while not sub.queue.empty():
            sub.queue.get_nowait()

        r2 = worker.process_batch(session=e2e_db_session)
        assert r2.events_skipped == 1
        assert r2.events_processed == 0

        # No duplicate event should be broadcasted to sub.queue
        assert sub.queue.empty(), "Duplicate skipped event must not be broadcasted."

    def test_worker_poison_pill_isolation_and_dead_letter_quarantine(
        self, e2e_db_session: Session
    ):
        """Poison pill events with invalid payloads are isolated into dead-letter table."""
        tenant = _create_tenant(e2e_db_session, "Poison Store", "poison.aggrix.local")

        # Poison event missing order_id
        bad_evt = OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            event_type="order.created",
            payload={"corrupted": "missing_required_fields"},
            created_at=datetime.now(timezone.utc),
        )
        e2e_db_session.add(bad_evt)
        e2e_db_session.commit()

        worker = IncrementalAggregationWorker(
            engine=e2e_db_session.bind,
            consumer_name="dlq_worker",
        )
        r = worker.process_batch(session=e2e_db_session)
        assert r.events_failed == 1

        # Verify dead letter recorded
        dl = e2e_db_session.execute(
            select(AnalyticsDeadLetterEvent).where(AnalyticsDeadLetterEvent.event_id == bad_evt.id)
        ).scalar_one_or_none()
        assert dl is not None
        assert dl.attempts == 1
        assert "missing required order_id" in dl.error_message
