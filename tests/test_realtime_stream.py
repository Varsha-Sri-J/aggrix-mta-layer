"""Automated test suite for Real-Time SSE Stream (Workstream 1).

Covers:
- Unauthenticated access rejection (401).
- Browser query param ?token= authentication.
- Tenant-aware stream delivery and strict tenant isolation (zero leakage).
- Store manager multi-tenant filtering.
- Platform admin global visibility.
- Last-Event-ID reconnection and replay from ring buffer.
- Disconnection cleanup and active subscriber tracking.
- Multiple concurrent client delivery.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.broadcaster import BroadcastEvent, broadcaster
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.main import create_application
from app.models.customer import Customer
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.user import User, UserRole


@pytest.fixture
def stream_db_session() -> Generator[Session, None, None]:
    """In-memory SQLite session with schema initialized."""
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
def stream_app(stream_db_session: Session):
    """FastAPI test app with overridden db dependency."""
    from app.database.connection import get_db

    app = create_application()
    app.dependency_overrides[get_db] = lambda: stream_db_session
    return app


@pytest.fixture
def stream_client(stream_app) -> Generator[TestClient, None, None]:
    """TestClient configured with overridden app."""
    with TestClient(stream_app) as client:
        yield client


@pytest.fixture(autouse=True)
def clean_broadcaster():
    """Ensure broadcaster has fresh state for every test."""
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
        hashed_password=hash_password("SuperSecret123!"),
        role=role.value,
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestRealTimeSSEStream:
    """Test suite for Server-Sent Events stream endpoint."""

    def test_stream_unauthorized_missing_token_401(self, stream_client: TestClient):
        """Streaming endpoint must reject requests missing bearer token with 401."""
        res = stream_client.get("/api/v1/analytics/stream")
        assert res.status_code == 401
        assert "Missing authentication token" in res.json()["detail"]

        # Alias route must also reject
        alias_res = stream_client.get("/api/analytics/stream")
        assert alias_res.status_code == 401

    def test_stream_token_in_query_parameter_for_eventsource(
        self, stream_client: TestClient, stream_db_session: Session
    ):
        """Native browser EventSource cannot send headers; verify ?token= query param succeeds."""
        tenant = _create_tenant(stream_db_session, "Store Alpha", "alpha.aggrix.local")
        user = _create_user(stream_db_session, "user@alpha.local", UserRole.TENANT_USER, tenant_id=tenant.id)
        token = create_access_token(subject=user.id, role=user.role, tenant_id=user.tenant_id)

        res = stream_client.get(f"/api/v1/analytics/stream?token={token}&max_events=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        assert "event: connected" in res.text
        assert '"status": "connected"' in res.text
        assert user.role in res.text

    def test_stream_strict_tenant_isolation(
        self, stream_client: TestClient, stream_db_session: Session
    ):
        """Tenant users must receive only events for their own store and never cross-tenant events."""
        tenant_a = _create_tenant(stream_db_session, "Store A", "a.aggrix.local")
        tenant_b = _create_tenant(stream_db_session, "Store B", "b.aggrix.local")

        user_a = _create_user(stream_db_session, "user@a.local", UserRole.TENANT_USER, tenant_id=tenant_a.id)
        token_a = create_access_token(subject=user_a.id, role=user_a.role, tenant_id=user_a.tenant_id)

        sub_a = broadcaster.subscribe(
            user_id=user_a.id,
            role=user_a.role,
            authorized_tenant_ids={tenant_a.id},
        )

        # 1. Publish event for Tenant B
        broadcaster.publish_event(
            event_type="order.created",
            tenant_id=tenant_b.id,
            order_id=uuid.uuid4(),
            status="pending",
            total_amount=150.00,
            currency="USD",
            external_order_id="ORD-B-001",
        )

        # Queue for A must remain empty
        assert sub_a.queue.empty(), "Tenant A subscriber must NOT receive Tenant B event!"

        # 2. Publish event for Tenant A
        broadcaster.publish_event(
            event_type="order.created",
            tenant_id=tenant_a.id,
            order_id=uuid.uuid4(),
            status="pending",
            total_amount=75.50,
            currency="USD",
            external_order_id="ORD-A-001",
        )

        # Queue for A must have received the event
        assert not sub_a.queue.empty(), "Tenant A subscriber must receive Tenant A event."
        received = sub_a.queue.get_nowait()
        assert received is not None
        assert received.tenant_id == tenant_a.id
        assert received.external_order_id == "ORD-A-001"

    def test_stream_tenant_user_cannot_subscribe_to_other_tenant_filter(
        self, stream_client: TestClient, stream_db_session: Session
    ):
        """Tenant user requesting filter_tenant_id for a different store must receive 403."""
        tenant_a = _create_tenant(stream_db_session, "Store A", "a.aggrix.local")
        tenant_b = _create_tenant(stream_db_session, "Store B", "b.aggrix.local")

        user_a = _create_user(stream_db_session, "user@a.local", UserRole.TENANT_USER, tenant_id=tenant_a.id)
        token_a = create_access_token(subject=user_a.id, role=user_a.role, tenant_id=user_a.tenant_id)

        res = stream_client.get(
            f"/api/v1/analytics/stream?token={token_a}&tenant_id={tenant_b.id}"
        )
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]

    def test_stream_store_manager_receives_assigned_stores_only(
        self, stream_client: TestClient, stream_db_session: Session
    ):
        """Multi-store manager only receives events from assigned stores."""
        t1 = _create_tenant(stream_db_session, "Store 1", "s1.aggrix.local")
        t2 = _create_tenant(stream_db_session, "Store 2", "s2.aggrix.local")
        t3 = _create_tenant(stream_db_session, "Store 3", "s3.aggrix.local")

        mgr = _create_user(stream_db_session, "mgr@aggrix.local", UserRole.STORE_MANAGER)
        stream_db_session.add(ManagerTenantAssignment(user_id=mgr.id, tenant_id=t1.id))
        stream_db_session.add(ManagerTenantAssignment(user_id=mgr.id, tenant_id=t2.id))
        stream_db_session.commit()

        sub = broadcaster.subscribe(
            user_id=mgr.id,
            role=mgr.role,
            authorized_tenant_ids={t1.id, t2.id},
        )

        # Event for T3 (unassigned) -> skipped
        broadcaster.publish_event(
            event_type="order.created",
            tenant_id=t3.id,
            order_id=uuid.uuid4(),
            status="pending",
            total_amount=100.0,
            currency="USD",
        )
        assert sub.queue.empty()

        # Event for T1 (assigned) -> received
        broadcaster.publish_event(
            event_type="order.created",
            tenant_id=t1.id,
            order_id=uuid.uuid4(),
            status="pending",
            total_amount=200.0,
            currency="USD",
        )
        assert not sub.queue.empty()

    def test_stream_reconnection_last_event_id_replay(
        self, stream_client: TestClient, stream_db_session: Session
    ):
        """Clients reconnecting with Last-Event-ID must receive missed events from ring buffer."""
        tenant = _create_tenant(stream_db_session, "Replay Store", "replay.aggrix.local")
        user = _create_user(stream_db_session, "admin@aggrix.local", UserRole.PLATFORM_ADMIN)

        # Publish 3 events to populate history buffer
        ev1 = broadcaster.publish_event(
            event_type="order.created",
            tenant_id=tenant.id,
            order_id=uuid.uuid4(),
            status="pending",
            total_amount=50.0,
            currency="USD",
            external_order_id="ORD-001",
        )
        ev2 = broadcaster.publish_event(
            event_type="order.paid",
            tenant_id=tenant.id,
            order_id=uuid.uuid4(),
            status="paid",
            total_amount=100.0,
            currency="USD",
            external_order_id="ORD-002",
        )
        ev3 = broadcaster.publish_event(
            event_type="order.fulfilled",
            tenant_id=tenant.id,
            order_id=uuid.uuid4(),
            status="fulfilled",
            total_amount=150.0,
            currency="USD",
            external_order_id="ORD-003",
        )

        sub = broadcaster.subscribe(user.id, user.role, authorized_tenant_ids=None)

        # Request replay since ev1.id -> must receive ev2 and ev3
        replayed = broadcaster.get_events_since(ev1.id, sub)
        assert len(replayed) == 2
        assert replayed[0].id == ev2.id
        assert replayed[1].id == ev3.id

    def test_stream_client_disconnect_cleanup(
        self, stream_client: TestClient, stream_db_session: Session
    ):
        """Unsubscribing a client removes subscription and prevents memory leaks."""
        user_id = uuid.uuid4()
        initial_count = broadcaster.active_subscribers_count

        sub = broadcaster.subscribe(
            user_id=user_id,
            role=UserRole.PLATFORM_ADMIN.value,
            authorized_tenant_ids=None,
        )
        assert broadcaster.active_subscribers_count == initial_count + 1

        broadcaster.unsubscribe(sub.client_id)
        assert broadcaster.active_subscribers_count == initial_count

    def test_multiple_concurrent_clients(
        self, stream_client: TestClient, stream_db_session: Session
    ):
        """Multiple concurrent subscribers receive events matching their scopes independently."""
        tenant = _create_tenant(stream_db_session, "Multi Store", "multi.aggrix.local")

        subs = [
            broadcaster.subscribe(
                user_id=uuid.uuid4(),
                role=UserRole.TENANT_USER.value,
                authorized_tenant_ids={tenant.id},
            )
            for _ in range(5)
        ]

        assert broadcaster.active_subscribers_count == 5

        # Publish single event
        broadcaster.publish_event(
            event_type="order.created",
            tenant_id=tenant.id,
            order_id=uuid.uuid4(),
            status="pending",
            total_amount=99.99,
            currency="USD",
            external_order_id="ORD-CONCUR-1",
        )

        # All 5 subscribers must have received the event in their respective queues
        for s in subs:
            assert not s.queue.empty()
            ev = s.queue.get_nowait()
            assert ev is not None
            assert ev.external_order_id == "ORD-CONCUR-1"
            broadcaster.unsubscribe(s.client_id)

        assert broadcaster.active_subscribers_count == 0

    def test_broadcaster_concurrent_thread_publishing(self, stream_db_session: Session):
        """Verify thread-safe event publishing from multiple concurrent background threads."""
        import concurrent.futures
        broadcaster.clear_all()
        tenant_id = uuid.uuid4()

        sub = broadcaster.subscribe(
            user_id=uuid.uuid4(),
            role="platform_admin",
            authorized_tenant_ids=None,
        )

        def publish_task(idx: int):
            broadcaster.publish_event(
                event_type="order.created",
                tenant_id=tenant_id,
                order_id=uuid.uuid4(),
                status="pending",
                total_amount=float(idx * 10),
                currency="USD",
                external_order_id=f"ORD-THREAD-{idx}",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(publish_task, range(20)))

        # Subscriber queue should have received events without corruption
        received_ids = []
        while not sub.queue.empty():
            ev = sub.queue.get_nowait()
            if ev:
                received_ids.append(ev.external_order_id)

        assert len(received_ids) == 20
        assert len(set(received_ids)) == 20
        broadcaster.unsubscribe(sub.client_id)

    def test_broadcaster_deduplication(self, stream_db_session: Session):
        """Verify identical event IDs are deduplicated in the ring buffer."""
        broadcaster.clear_all()
        tid = uuid.uuid4()
        oid = uuid.uuid4()
        eid = "evt-fixed-id-12345"

        ev1 = broadcaster.publish_event(
            event_type="order.created",
            tenant_id=tid,
            order_id=oid,
            status="pending",
            total_amount=50.0,
            currency="USD",
            event_id=eid,
        )

        ev2 = broadcaster.publish_event(
            event_type="order.created",
            tenant_id=tid,
            order_id=oid,
            status="pending",
            total_amount=50.0,
            currency="USD",
            event_id=eid,
        )

        assert ev1.id == ev2.id == eid
        # Should only be recorded once in history buffer
        assert len(broadcaster._history_buffer) == 1

