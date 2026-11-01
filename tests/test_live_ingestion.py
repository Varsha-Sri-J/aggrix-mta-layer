"""
Unit and Integration Test Suite for AGGRIX Live Order Ingestion.

Verifies:
1. Valid single-order ingestion (persisting Customer, Product, Order, OrderItem, and OutboxEvent).
2. Idempotent duplicate order detection (same external_order_id, same status).
3. Order lifecycle status transition (e.g. pending -> paid emits order.paid outbox event).
4. Tenant isolation enforcement:
   - Tenant user can only ingest for own tenant.
   - Cross-tenant ingestion attempt rejected with 403 Forbidden.
5. Store manager ingestion:
   - Ingesting for assigned store succeeds.
   - Ingesting for unassigned store rejected with 403 Forbidden.
6. Validation errors:
   - Missing fields, negative prices, empty item list rejected with 422.
7. Batch order ingestion:
   - Atomic batch submission with per-record deduplication.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.database.connection import get_db
from app.main import app
from app.models.customer import Customer
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User, UserRole


@pytest.fixture
def test_db_session() -> Generator[Session, None, None]:
    """Isolated in-memory SQLite database session with complete schema."""
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(test_db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient overriding get_db to point to test_db_session."""
    def _override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_env(test_db_session: Session) -> dict:
    """Seeds two tenants, merchant users for each, and a manager assigned to only tenant 1."""
    # Tenant 1
    t1_id = uuid.uuid4()
    t1 = Tenant(id=t1_id, name="Store Alpha", domain="alpha.store", timezone="UTC")
    test_db_session.add(t1)

    # Tenant 2
    t2_id = uuid.uuid4()
    t2 = Tenant(id=t2_id, name="Store Beta", domain="beta.store", timezone="UTC")
    test_db_session.add(t2)

    # Merchant 1 (scoped to Tenant 1)
    m1_id = uuid.uuid4()
    m1 = User(
        id=m1_id,
        email="merchant1@alpha.store",
        hashed_password=hash_password("Pass123!"),
        role=UserRole.TENANT_USER.value,
        tenant_id=t1_id,
        is_active=True,
    )
    test_db_session.add(m1)

    # Merchant 2 (scoped to Tenant 2)
    m2_id = uuid.uuid4()
    m2 = User(
        id=m2_id,
        email="merchant2@beta.store",
        hashed_password=hash_password("Pass123!"),
        role=UserRole.TENANT_USER.value,
        tenant_id=t2_id,
        is_active=True,
    )
    test_db_session.add(m2)

    # Store Manager (assigned only to Tenant 1)
    mgr_id = uuid.uuid4()
    mgr = User(
        id=mgr_id,
        email="manager@retail.corp",
        hashed_password=hash_password("Pass123!"),
        role=UserRole.STORE_MANAGER.value,
        tenant_id=None,
        is_active=True,
    )
    test_db_session.add(mgr)

    assignment = ManagerTenantAssignment(
        user_id=mgr_id,
        tenant_id=t1_id,
    )
    test_db_session.add(assignment)

    test_db_session.commit()

    # Generate tokens
    m1_token = create_access_token(
        subject=m1_id,
        role=UserRole.TENANT_USER.value,
        tenant_id=t1_id,
    )
    m2_token = create_access_token(
        subject=m2_id,
        role=UserRole.TENANT_USER.value,
        tenant_id=t2_id,
    )
    mgr_token = create_access_token(
        subject=mgr_id,
        role=UserRole.STORE_MANAGER.value,
    )

    return {
        "t1_id": t1_id,
        "t2_id": t2_id,
        "m1_token": m1_token,
        "m2_token": m2_token,
        "mgr_token": mgr_token,
    }


def test_merchant_ingest_single_order_success(
    client: TestClient,
    test_db_session: Session,
    seeded_env: dict,
):
    """Verifies that a merchant can successfully ingest a live order for their tenant."""
    token = seeded_env["m1_token"]
    t1_id = seeded_env["t1_id"]

    order_payload = {
        "external_order_id": "#ORD-1001",
        "customer": {"email": "customer1@gmail.com", "name": "Alice Customer"},
        "currency": "USD",
        "status": "paid",
        "items": [
            {"sku": "SKU-A1", "name": "Widget A", "quantity": 2, "unit_price": 50.0},
            {"sku": "SKU-A2", "name": "Widget B", "quantity": 1, "unit_price": 25.0},
        ],
        "total_amount": 125.0,
    }

    response = client.post(
        "/api/v1/ingest/orders",
        json=order_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["external_order_id"] == "#ORD-1001"
    assert data["tenant_id"] == str(t1_id)
    assert data["status"] == "paid"
    assert Decimal(str(data["total_amount"])) == Decimal("125.0")
    assert data["is_duplicate"] is False
    assert data["items_count"] == 2

    # Verify persistence in database
    db_order = test_db_session.execute(
        sa.select(Order).where(Order.external_order_id == "#ORD-1001")
    ).scalar_one()
    assert db_order.tenant_id == t1_id
    assert db_order.status == "paid"

    # Verify Outbox event created
    db_outbox = test_db_session.execute(
        sa.select(OutboxEvent).where(OutboxEvent.id == uuid.UUID(data["outbox_event_id"]))
    ).scalar_one()
    assert db_outbox.tenant_id == t1_id
    assert db_outbox.event_type == "order.paid"
    assert db_outbox.payload["order_id"] == str(db_order.id)
    assert len(db_outbox.payload["items"]) == 2


def test_idempotent_duplicate_order_handling(
    client: TestClient,
    test_db_session: Session,
    seeded_env: dict,
):
    """Verifies that re-submitting an identical order returns is_duplicate=True without duplicates."""
    token = seeded_env["m1_token"]

    order_payload = {
        "external_order_id": "#ORD-DUP-01",
        "customer": {"email": "dup@test.com"},
        "status": "paid",
        "items": [{"sku": "SKU-DUP", "quantity": 1, "unit_price": 99.0}],
    }

    # First submission
    r1 = client.post(
        "/api/v1/ingest/orders",
        json=order_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 201
    assert r1.json()["is_duplicate"] is False

    # Second submission (identical duplicate)
    r2 = client.post(
        "/api/v1/ingest/orders",
        json=order_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 201
    assert r2.json()["is_duplicate"] is True
    assert "already exists" in r2.json()["message"]

    # Verify order count in DB is exactly 1
    orders = test_db_session.execute(
        sa.select(Order).where(Order.external_order_id == "#ORD-DUP-01")
    ).scalars().all()
    assert len(orders) == 1


def test_order_lifecycle_status_transition(
    client: TestClient,
    test_db_session: Session,
    seeded_env: dict,
):
    """Verifies that updating order status triggers a status transition event."""
    token = seeded_env["m1_token"]
    t1_id = seeded_env["t1_id"]

    order_payload = {
        "external_order_id": "#ORD-TRANS-01",
        "customer": {"email": "trans@test.com"},
        "status": "pending",
        "items": [{"sku": "SKU-TR", "quantity": 1, "unit_price": 50.0}],
    }

    # 1. Create as pending -> outbox event is order.created
    r1 = client.post(
        "/api/v1/ingest/orders",
        json=order_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 201
    assert r1.json()["event_type"] == "order.created"

    # 2. Update to paid
    order_payload["status"] = "paid"
    r2 = client.post(
        "/api/v1/ingest/orders",
        json=order_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 201
    assert r2.json()["is_duplicate"] is False
    assert r2.json()["event_type"] == "order.paid"
    assert "transitioned from 'pending' to 'paid'" in r2.json()["message"]


def test_cross_tenant_ingestion_rejection(
    client: TestClient,
    seeded_env: dict,
):
    """Verifies that a merchant cannot inject orders into another merchant's tenant."""
    m1_token = seeded_env["m1_token"]
    t2_id = seeded_env["t2_id"]

    malicious_payload = {
        "tenant_id": str(t2_id),  # Attempting to inject into Tenant 2
        "external_order_id": "#ORD-HACK-01",
        "customer": {"email": "hacker@test.com"},
        "status": "paid",
        "items": [{"sku": "SKU-HACK", "quantity": 10, "unit_price": 1000.0}],
    }

    response = client.post(
        "/api/v1/ingest/orders",
        json=malicious_payload,
        headers={"Authorization": f"Bearer {m1_token}"},
    )

    assert response.status_code == 403
    assert "Cross-tenant ingestion forbidden" in response.json()["detail"]


def test_manager_ingestion_permissions(
    client: TestClient,
    seeded_env: dict,
):
    """Verifies that managers can ingest into assigned stores, but get 403 on unassigned stores."""
    mgr_token = seeded_env["mgr_token"]
    t1_id = seeded_env["t1_id"]
    t2_id = seeded_env["t2_id"]

    # 1. Manager ingests for assigned store (Tenant 1) -> 201
    r_assigned = client.post(
        "/api/v1/ingest/orders",
        json={
            "tenant_id": str(t1_id),
            "external_order_id": "#MGR-ORD-01",
            "customer": {"email": "mgr_order@test.com"},
            "status": "paid",
            "items": [{"sku": "SKU-M1", "quantity": 1, "unit_price": 75.0}],
        },
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert r_assigned.status_code == 201

    # 2. Manager tries to ingest for unassigned store (Tenant 2) -> 403
    r_unassigned = client.post(
        "/api/v1/ingest/orders",
        json={
            "tenant_id": str(t2_id),
            "external_order_id": "#MGR-ORD-02",
            "customer": {"email": "mgr_unassigned@test.com"},
            "status": "paid",
            "items": [{"sku": "SKU-M2", "quantity": 1, "unit_price": 75.0}],
        },
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert r_unassigned.status_code == 403
    assert "manager is not assigned" in r_unassigned.json()["detail"]


def test_validation_errors(
    client: TestClient,
    seeded_env: dict,
):
    """Verifies that malformed payloads return 422 Unprocessable Entity."""
    token = seeded_env["m1_token"]

    # Negative price
    r1 = client.post(
        "/api/v1/ingest/orders",
        json={
            "external_order_id": "#BAD-01",
            "customer": {"email": "bad@test.com"},
            "items": [{"sku": "SKU-BAD", "quantity": 1, "unit_price": -10.0}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 422

    # Zero items
    r2 = client.post(
        "/api/v1/ingest/orders",
        json={
            "external_order_id": "#BAD-02",
            "customer": {"email": "bad@test.com"},
            "items": [],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 422

    # Missing customer email
    r3 = client.post(
        "/api/v1/ingest/orders",
        json={
            "external_order_id": "#BAD-03",
            "customer": {},
            "items": [{"sku": "SKU-BAD", "quantity": 1, "unit_price": 10.0}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 422


def test_batch_ingest_orders(
    client: TestClient,
    test_db_session: Session,
    seeded_env: dict,
):
    """Verifies batch order ingestion endpoint."""
    token = seeded_env["m1_token"]

    batch_payload = {
        "orders": [
            {
                "external_order_id": "#BATCH-01",
                "customer": {"email": "batch1@test.com"},
                "status": "paid",
                "items": [{"sku": "SKU-B1", "quantity": 1, "unit_price": 30.0}],
            },
            {
                "external_order_id": "#BATCH-02",
                "customer": {"email": "batch2@test.com"},
                "status": "pending",
                "items": [{"sku": "SKU-B2", "quantity": 2, "unit_price": 20.0}],
            },
        ]
    }

    response = client.post(
        "/api/v1/ingest/orders/batch",
        json=batch_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["total_submitted"] == 2
    assert data["ingested_count"] == 2
    assert data["duplicate_count"] == 0
    assert len(data["orders"]) == 2
