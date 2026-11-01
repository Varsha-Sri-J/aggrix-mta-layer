"""Automated test suite for Real-Time Analytics APIs (Workstream 2).

Covers:
- Store switcher endpoint (/api/v1/analytics/tenants) across roles.
- Order status distribution (/status-distribution) with percentages and sales.
- Recent activity feed (/recent-orders) with customer details and pagination.
- Composite dashboard overview (/overview).
- Average Order Value (AOV) and active customer count calculations.
- Strict tenant authorization and isolation enforcement.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.main import create_application
from app.models.customer import Customer
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User, UserRole


@pytest.fixture
def ext_db_session() -> Generator[Session, None, None]:
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
def ext_app(ext_db_session: Session):
    """FastAPI test app with overridden db dependency."""
    from app.database.connection import get_db

    app = create_application()
    app.dependency_overrides[get_db] = lambda: ext_db_session
    return app


@pytest.fixture
def ext_client(ext_app) -> Generator[TestClient, None, None]:
    """TestClient configured with overridden app."""
    with TestClient(ext_app) as client:
        yield client


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
        hashed_password=hash_password("SecurePassword123!"),
        role=role.value,
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestExtendedAnalyticsAPIs:
    """Test suite for extended real-time analytics query endpoints."""

    def test_accessible_tenants_platform_admin_sees_all(
        self, ext_client: TestClient, ext_db_session: Session
    ):
        """Platform admin must see all stores in the database."""
        t1 = _create_tenant(ext_db_session, "Store 1", "s1.local")
        t2 = _create_tenant(ext_db_session, "Store 2", "s2.local")
        admin = _create_user(ext_db_session, "admin@local", UserRole.PLATFORM_ADMIN)

        token = create_access_token(subject=admin.id, role=admin.role, tenant_id=admin.tenant_id)
        res = ext_client.get(
            "/api/v1/analytics/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        tenant_ids = {t["id"] for t in data["tenants"]}
        assert str(t1.id) in tenant_ids
        assert str(t2.id) in tenant_ids

    def test_accessible_tenants_store_manager_sees_assigned_only(
        self, ext_client: TestClient, ext_db_session: Session
    ):
        """Store manager must see only explicitly assigned stores."""
        t1 = _create_tenant(ext_db_session, "Store 1", "s1.local")
        t2 = _create_tenant(ext_db_session, "Store 2", "s2.local")
        t3 = _create_tenant(ext_db_session, "Store 3", "s3.local")

        mgr = _create_user(ext_db_session, "mgr@local", UserRole.STORE_MANAGER)
        ext_db_session.add(ManagerTenantAssignment(user_id=mgr.id, tenant_id=t1.id))
        ext_db_session.add(ManagerTenantAssignment(user_id=mgr.id, tenant_id=t3.id))
        ext_db_session.commit()

        token = create_access_token(subject=mgr.id, role=mgr.role, tenant_id=mgr.tenant_id)
        res = ext_client.get(
            "/api/v1/analytics/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        tenant_ids = {t["id"] for t in data["tenants"]}
        assert str(t1.id) in tenant_ids
        assert str(t3.id) in tenant_ids
        assert str(t2.id) not in tenant_ids

    def test_accessible_tenants_tenant_user_sees_own_only(
        self, ext_client: TestClient, ext_db_session: Session
    ):
        """Tenant user must see only their own home store."""
        t1 = _create_tenant(ext_db_session, "Store 1", "s1.local")
        t2 = _create_tenant(ext_db_session, "Store 2", "s2.local")

        user = _create_user(ext_db_session, "user1@local", UserRole.TENANT_USER, tenant_id=t1.id)
        token = create_access_token(subject=user.id, role=user.role, tenant_id=user.tenant_id)

        res = ext_client.get(
            "/api/v1/analytics/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["tenants"][0]["id"] == str(t1.id)

    def test_order_status_distribution(
        self, ext_client: TestClient, ext_db_session: Session
    ):
        """Status distribution endpoint must return correct counts, revenue, and percentages."""
        tenant = _create_tenant(ext_db_session, "Status Store", "status.local")
        customer = Customer(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="cust@status.local",
            name="Alice Smith",
        )
        ext_db_session.add(customer)
        ext_db_session.commit()

        # Seed orders across statuses
        orders = [
            Order(id=uuid.uuid4(), tenant_id=tenant.id, customer_id=customer.id, external_order_id="ORD-1", total_amount=Decimal("100.00"), currency="USD", status="pending"),
            Order(id=uuid.uuid4(), tenant_id=tenant.id, customer_id=customer.id, external_order_id="ORD-2", total_amount=Decimal("200.00"), currency="USD", status="paid"),
            Order(id=uuid.uuid4(), tenant_id=tenant.id, customer_id=customer.id, external_order_id="ORD-3", total_amount=Decimal("300.00"), currency="USD", status="fulfilled"),
            Order(id=uuid.uuid4(), tenant_id=tenant.id, customer_id=customer.id, external_order_id="ORD-4", total_amount=Decimal("50.00"), currency="USD", status="cancelled"),
        ]
        ext_db_session.add_all(orders)
        ext_db_session.commit()

        user = _create_user(ext_db_session, "user@status.local", UserRole.TENANT_USER, tenant_id=tenant.id)
        token = create_access_token(subject=user.id, role=user.role, tenant_id=user.tenant_id)

        res = ext_client.get(
            f"/api/v1/analytics/tenants/{tenant.id}/status-distribution",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_orders"] == 4

        statuses = {s["status"]: s for s in data["statuses"]}
        assert statuses["pending"]["orders_count"] == 1
        assert float(statuses["pending"]["gross_sales"]) == 100.0
        assert statuses["pending"]["percentage"] == 25.0

        assert statuses["paid"]["orders_count"] == 1
        assert float(statuses["paid"]["gross_sales"]) == 200.0

        assert statuses["fulfilled"]["orders_count"] == 1
        assert float(statuses["fulfilled"]["gross_sales"]) == 300.0

        assert statuses["cancelled"]["orders_count"] == 1
        assert float(statuses["cancelled"]["gross_sales"]) == 50.0

    def test_recent_orders_feed_pagination(
        self, ext_client: TestClient, ext_db_session: Session
    ):
        """Recent orders feed must return chronological orders with customer details."""
        tenant = _create_tenant(ext_db_session, "Feed Store", "feed.local")
        customer = Customer(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="buyer@feed.local",
            name="Bob Jones",
        )
        ext_db_session.add(customer)
        ext_db_session.commit()

        # Add 3 orders
        for i in range(3):
            o = Order(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                customer_id=customer.id,
                external_order_id=f"FEED-ORD-{i+1}",
                total_amount=Decimal(f"{50 * (i+1)}.00"),
                currency="USD",
                status="paid",
            )
            ext_db_session.add(o)
        ext_db_session.commit()

        user = _create_user(ext_db_session, "feed_user@local", UserRole.TENANT_USER, tenant_id=tenant.id)
        token = create_access_token(subject=user.id, role=user.role, tenant_id=user.tenant_id)

        res = ext_client.get(
            f"/api/v1/analytics/tenants/{tenant.id}/recent-orders?page=1&page_size=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["pagination"]["total_records"] == 3
        assert data["pagination"]["total_pages"] == 2
        assert len(data["data"]) == 2
        assert data["data"][0]["customer_name"] == "Bob Jones"
        assert data["data"][0]["customer_email"] == "buyer@feed.local"

    def test_tenant_overview_composite_endpoint(
        self, ext_client: TestClient, ext_db_session: Session
    ):
        """Overview endpoint combines summary, status distribution, recent orders, and top products."""
        tenant = _create_tenant(ext_db_session, "Overview Store", "overview.local")
        user = _create_user(ext_db_session, "admin@overview.local", UserRole.PLATFORM_ADMIN)
        token = create_access_token(subject=user.id, role=user.role, tenant_id=user.tenant_id)

        res = ext_client.get(
            f"/api/v1/analytics/tenants/{tenant.id}/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["tenant_id"] == str(tenant.id)
        assert data["tenant_name"] == "Overview Store"
        assert "summary" in data
        assert "status_distribution" in data
        assert "recent_orders" in data
        assert "top_products" in data

    def test_average_order_value_and_active_customers_in_summary(
        self, ext_client: TestClient, ext_db_session: Session
    ):
        """Tenant summary must calculate AOV = gross_sales / total_orders and count active buyers."""
        tenant = _create_tenant(ext_db_session, "AOV Store", "aov.local")
        c1 = Customer(id=uuid.uuid4(), tenant_id=tenant.id, email="c1@aov.local", name="Buyer One")
        c2 = Customer(id=uuid.uuid4(), tenant_id=tenant.id, email="c2@aov.local", name="Buyer Two")
        ext_db_session.add_all([c1, c2])
        ext_db_session.commit()

        # Seed precomputed daily metric: 2 orders, $300 gross sales
        metric = DailyTenantMetric(
            tenant_id=tenant.id,
            metric_date=datetime.now(timezone.utc).date(),
            currency="USD",
            orders_count=2,
            gross_sales=Decimal("300.00"),
            net_sales=Decimal("300.00"),
            pending_orders_count=0,
            pending_sales=Decimal("0.00"),
            cancelled_orders_count=0,
            cancelled_sales=Decimal("0.00"),
        )
        ext_db_session.add(metric)

        # Seed raw orders for active customers count
        o1 = Order(id=uuid.uuid4(), tenant_id=tenant.id, customer_id=c1.id, external_order_id="AOV-1", total_amount=Decimal("100.00"), currency="USD", status="paid")
        o2 = Order(id=uuid.uuid4(), tenant_id=tenant.id, customer_id=c2.id, external_order_id="AOV-2", total_amount=Decimal("200.00"), currency="USD", status="paid")
        ext_db_session.add_all([o1, o2])
        ext_db_session.commit()

        user = _create_user(ext_db_session, "user@aov.local", UserRole.TENANT_USER, tenant_id=tenant.id)
        token = create_access_token(subject=user.id, role=user.role, tenant_id=user.tenant_id)

        res = ext_client.get(
            f"/api/v1/analytics/tenants/{tenant.id}/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_orders"] == 2
        assert float(data["gross_sales"]) == 300.00
        # AOV = 300 / 2 = 150.00
        assert float(data["average_order_value"]) == 150.00
        # 2 distinct customers
        assert data["active_customers_count"] == 2
