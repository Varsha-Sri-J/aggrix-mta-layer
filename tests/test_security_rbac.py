"""
Comprehensive Security, Authentication, and RBAC Test Suite for AGGRIX.

Verifies:
1. Authentication Security:
   - Missing Authorization header (401 Unauthorized)
   - Invalid token signature (401 Unauthorized)
   - Malformed tokens (401 Unauthorized)
   - Expired JWT token rejection (401 Unauthorized)
   - Deactivated user rejection (403 Forbidden)
   - Login credential validation and bcrypt password hashing
   - User profile endpoint (/api/v1/auth/me)
2. Role-Based Access Control (RBAC):
   - Tenant user accessing own tenant (200 OK)
   - Tenant user accessing another tenant (403 Forbidden)
   - Tenant user accessing manager routes (403 Forbidden)
   - Tenant user accessing platform admin routes (403 Forbidden)
   - Multi-store manager accessing assigned tenants (200 OK)
   - Multi-store manager accessing unassigned tenant (403 Forbidden)
   - Multi-store manager combined summary (/api/v1/analytics/manager/summary)
   - Multi-store manager store breakdown (/api/v1/analytics/manager/stores)
   - Multi-store manager store comparison (/api/v1/analytics/manager/compare)
   - Multi-store manager with empty assignments (200 OK empty results)
   - Multi-store manager accessing platform admin routes (403 Forbidden)
   - Platform administrator accessing any tenant (200 OK)
   - Platform administrator accessing platform summary (/api/v1/analytics/platform/summary)
3. Accounting & Isolation Integrity:
   - Currency separation on manager & platform endpoints (never combine different currencies)
   - Date range filtering
   - No data leakage between tenants
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.database.connection import get_db
from app.main import app

from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.tenant import Tenant
from app.models.user import User, UserRole


@pytest.fixture
def rbac_engine() -> Generator[sa.Engine, None, None]:
    """Isolated, thread-safe in-memory SQLite engine for RBAC testing."""
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
def rbac_session_factory(rbac_engine: sa.Engine) -> sessionmaker:
    return sessionmaker(bind=rbac_engine, expire_on_commit=False)


@pytest.fixture
def rbac_session(rbac_session_factory: sessionmaker) -> Generator[Session, None, None]:
    sess = rbac_session_factory()
    yield sess
    sess.close()


@pytest.fixture
def client(rbac_session_factory: sessionmaker) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with isolated session dependency override."""
    def _override_get_db():
        db = rbac_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def setup_rbac_environment(rbac_session: Session):
    """
    Sets up a full multi-tenant RBAC environment:
    - Store 1: Alpha Store (Tenant 1)
    - Store 2: Beta Store (Tenant 2)
    - Store 3: Gamma Store (Tenant 3)
    - Users:
      * user_alpha: Tenant User for Store 1
      * user_beta: Tenant User for Store 2
      * manager_1_2: Store Manager assigned to Store 1 and Store 2 (NOT Store 3)
      * manager_empty: Store Manager with 0 assigned stores
      * admin_user: Platform Administrator
      * inactive_user: Deactivated user
    - Daily Metrics seeded for all 3 stores (Store 1: USD, Store 2: EUR, Store 3: GBP).
    """
    # 1. Tenants
    t1 = Tenant(id=uuid.uuid4(), name="Alpha Store", domain="alpha.store.test", timezone="UTC")
    t2 = Tenant(id=uuid.uuid4(), name="Beta Store", domain="beta.store.test", timezone="UTC")
    t3 = Tenant(id=uuid.uuid4(), name="Gamma Store", domain="gamma.store.test", timezone="UTC")
    rbac_session.add_all([t1, t2, t3])
    rbac_session.commit()

    # 2. Users
    pw_hash = hash_password("ValidPassword123!")

    user_alpha = User(
        id=uuid.uuid4(),
        email="user.alpha@store.test",
        hashed_password=pw_hash,
        role=UserRole.TENANT_USER.value,
        is_active=True,
        tenant_id=t1.id,
    )
    user_beta = User(
        id=uuid.uuid4(),
        email="user.beta@store.test",
        hashed_password=pw_hash,
        role=UserRole.TENANT_USER.value,
        is_active=True,
        tenant_id=t2.id,
    )
    manager_1_2 = User(
        id=uuid.uuid4(),
        email="manager.1.2@store.test",
        hashed_password=pw_hash,
        role=UserRole.STORE_MANAGER.value,
        is_active=True,
        tenant_id=None,
    )
    manager_empty = User(
        id=uuid.uuid4(),
        email="manager.empty@store.test",
        hashed_password=pw_hash,
        role=UserRole.STORE_MANAGER.value,
        is_active=True,
        tenant_id=None,
    )
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@aggrix.test",
        hashed_password=pw_hash,
        role=UserRole.PLATFORM_ADMIN.value,
        is_active=True,
        tenant_id=None,
    )
    inactive_user = User(
        id=uuid.uuid4(),
        email="inactive@store.test",
        hashed_password=pw_hash,
        role=UserRole.TENANT_USER.value,
        is_active=False,
        tenant_id=t1.id,
    )
    rbac_session.add_all([user_alpha, user_beta, manager_1_2, manager_empty, admin_user, inactive_user])
    rbac_session.commit()

    # 3. Manager Assignments: manager_1_2 is assigned to Store 1 and Store 2 ONLY
    assign_1 = ManagerTenantAssignment(id=uuid.uuid4(), user_id=manager_1_2.id, tenant_id=t1.id)
    assign_2 = ManagerTenantAssignment(id=uuid.uuid4(), user_id=manager_1_2.id, tenant_id=t2.id)
    rbac_session.add_all([assign_1, assign_2])
    rbac_session.commit()

    # 4. Metrics
    d = date(2026, 9, 15)
    # Store 1 metrics (USD)
    m1 = DailyTenantMetric(
        tenant_id=t1.id,
        metric_date=d,
        currency="USD",
        orders_count=100,
        gross_sales=Decimal("10000.00"),
        net_sales=Decimal("9000.00"),
        pending_orders_count=10,
        pending_sales=Decimal("1000.00"),
        cancelled_orders_count=5,
        cancelled_sales=Decimal("500.00"),
    )
    # Store 2 metrics (EUR)
    m2 = DailyTenantMetric(
        tenant_id=t2.id,
        metric_date=d,
        currency="EUR",
        orders_count=50,
        gross_sales=Decimal("6000.00"),
        net_sales=Decimal("5500.00"),
        pending_orders_count=5,
        pending_sales=Decimal("500.00"),
        cancelled_orders_count=2,
        cancelled_sales=Decimal("200.00"),
    )
    # Store 3 metrics (GBP)
    m3 = DailyTenantMetric(
        tenant_id=t3.id,
        metric_date=d,
        currency="GBP",
        orders_count=30,
        gross_sales=Decimal("4000.00"),
        net_sales=Decimal("3800.00"),
        pending_orders_count=2,
        pending_sales=Decimal("200.00"),
        cancelled_orders_count=1,
        cancelled_sales=Decimal("100.00"),
    )
    rbac_session.add_all([m1, m2, m3])
    rbac_session.commit()

    # 5. Tokens
    token_alpha = create_access_token(user_alpha.id, "tenant_user", t1.id)
    token_beta = create_access_token(user_beta.id, "tenant_user", t2.id)
    token_manager = create_access_token(manager_1_2.id, "store_manager", None)
    token_manager_empty = create_access_token(manager_empty.id, "store_manager", None)
    token_admin = create_access_token(admin_user.id, "platform_admin", None)
    token_inactive = create_access_token(inactive_user.id, "tenant_user", t1.id)

    return {
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "user_alpha": user_alpha,
        "user_beta": user_beta,
        "manager_1_2": manager_1_2,
        "manager_empty": manager_empty,
        "admin_user": admin_user,
        "token_alpha": token_alpha,
        "token_beta": token_beta,
        "token_manager": token_manager,
        "token_manager_empty": token_manager_empty,
        "token_admin": token_admin,
        "token_inactive": token_inactive,
    }


class TestAuthenticationSecurity:
    """Tests authentication enforcement, JWT validation, expiration, and user status."""

    def test_missing_authorization_header_returns_401(
        self, client: TestClient, setup_rbac_environment
    ):
        """Unauthenticated requests are rejected with 401 Unauthorized."""
        t1 = setup_rbac_environment["t1"]
        endpoints = [
            f"/api/v1/analytics/tenants/{t1.id}/summary",
            f"/api/v1/analytics/tenants/{t1.id}/daily",
            f"/api/v1/analytics/tenants/{t1.id}/products",
            "/api/v1/analytics/manager/summary",
            "/api/v1/analytics/manager/stores",
            "/api/v1/analytics/manager/compare",
            "/api/v1/analytics/platform/summary",
            "/api/v1/auth/me",
        ]
        for ep in endpoints:
            resp = client.get(ep)
            assert resp.status_code == 401, f"Expected 401 for {ep}, got {resp.status_code}"
            assert "missing" in resp.json()["detail"].lower()

    def test_invalid_jwt_signature_returns_401(
        self, client: TestClient, setup_rbac_environment
    ):
        """Tampered or invalid JWT signatures are rejected with 401."""
        t1 = setup_rbac_environment["t1"]
        # Valid structure but forged with random key
        import jwt
        forged = jwt.encode(
            {"sub": str(uuid.uuid4()), "role": "platform_admin", "exp": 9999999999, "iat": 1},
            "wrong-secret-key-that-does-not-match-settings-32b",
            algorithm="HS256",
        )
        resp = client.get(
            f"/api/v1/analytics/tenants/{t1.id}/summary",
            headers={"Authorization": f"Bearer {forged}"},
        )
        assert resp.status_code == 401
        assert "could not validate credentials" in resp.json()["detail"].lower()

    def test_malformed_token_returns_401(
        self, client: TestClient, setup_rbac_environment
    ):
        """Malformed garbage tokens are rejected with 401."""
        t1 = setup_rbac_environment["t1"]
        resp = client.get(
            f"/api/v1/analytics/tenants/{t1.id}/summary",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        assert resp.status_code == 401

    def test_expired_jwt_token_returns_401(
        self, client: TestClient, setup_rbac_environment
    ):
        """Tokens past expiration are rejected with 401 and specific expiration error."""
        t1 = setup_rbac_environment["t1"]
        user_alpha = setup_rbac_environment["user_alpha"]
        # Generate token with negative expiration
        expired_token = create_access_token(
            subject=user_alpha.id,
            role="tenant_user",
            tenant_id=t1.id,
            expires_delta=timedelta(seconds=-10),
        )
        resp = client.get(
            f"/api/v1/analytics/tenants/{t1.id}/summary",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    def test_deactivated_user_account_returns_403(
        self, client: TestClient, setup_rbac_environment
    ):
        """Valid token for an inactive/deactivated user account returns 403 Forbidden."""
        t1 = setup_rbac_environment["t1"]
        token_inactive = setup_rbac_environment["token_inactive"]
        resp = client.get(
            f"/api/v1/analytics/tenants/{t1.id}/summary",
            headers={"Authorization": f"Bearer {token_inactive}"},
        )
        assert resp.status_code == 403
        assert "deactivated" in resp.json()["detail"].lower()

    def test_login_flow_and_me_profile(
        self, client: TestClient, setup_rbac_environment
    ):
        """Login validates bcrypt password hash and issues a working JWT token."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "manager.1.2@store.test", "password": "ValidPassword123!"},
        )
        assert resp.status_code == 200
        token_data = resp.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"
        assert token_data["role"] == "store_manager"
        assert len(token_data["assigned_tenant_ids"]) == 2

        # Verify access token works on /auth/me
        token = token_data["access_token"]
        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["email"] == "manager.1.2@store.test"
        assert me_data["role"] == "store_manager"
        assert len(me_data["assigned_tenant_ids"]) == 2

    def test_login_invalid_password_returns_401(
        self, client: TestClient, setup_rbac_environment
    ):
        """Incorrect password returns 401 Unauthorized."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "manager.1.2@store.test", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401
        assert "invalid email or password" in resp.json()["detail"].lower()

    def test_login_unknown_email_returns_401(
        self, client: TestClient, setup_rbac_environment
    ):
        """Non-existent email returns 401 Unauthorized."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@store.test", "password": "SomePassword123!"},
        )
        assert resp.status_code == 401


class TestRBACTenantUser:
    """Verifies Tenant User permissions and strict tenant boundaries."""

    def test_tenant_user_access_own_tenant_success(
        self, client: TestClient, setup_rbac_environment
    ):
        """Tenant user can access all analytics endpoints for their own tenant."""
        t1 = setup_rbac_environment["t1"]
        token_alpha = setup_rbac_environment["token_alpha"]
        headers = {"Authorization": f"Bearer {token_alpha}"}

        # 1. Summary
        resp = client.get(f"/api/v1/analytics/tenants/{t1.id}/summary", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == str(t1.id)
        assert resp.json()["total_orders"] == 100

        # 2. Daily
        resp_daily = client.get(f"/api/v1/analytics/tenants/{t1.id}/daily", headers=headers)
        assert resp_daily.status_code == 200

        # 3. Products
        resp_prod = client.get(f"/api/v1/analytics/tenants/{t1.id}/products", headers=headers)
        assert resp_prod.status_code == 200

    def test_tenant_user_access_other_tenant_rejected_403(
        self, client: TestClient, setup_rbac_environment
    ):
        """Tenant user attempting to access another tenant in the URL receives 403 Forbidden."""
        t2 = setup_rbac_environment["t2"]
        token_alpha = setup_rbac_environment["token_alpha"]
        headers = {"Authorization": f"Bearer {token_alpha}"}

        endpoints = [
            f"/api/v1/analytics/tenants/{t2.id}/summary",
            f"/api/v1/analytics/tenants/{t2.id}/daily",
            f"/api/v1/analytics/tenants/{t2.id}/products",
        ]
        for ep in endpoints:
            resp = client.get(ep, headers=headers)
            assert resp.status_code == 403, f"Expected 403 for {ep}, got {resp.status_code}"
            assert "access denied" in resp.json()["detail"].lower()

    def test_tenant_user_cannot_access_manager_or_platform_endpoints(
        self, client: TestClient, setup_rbac_environment
    ):
        """Tenant user attempting to query manager or platform endpoints receives 403 Forbidden."""
        token_alpha = setup_rbac_environment["token_alpha"]
        headers = {"Authorization": f"Bearer {token_alpha}"}

        forbidden_routes = [
            "/api/v1/analytics/manager/summary",
            "/api/v1/analytics/manager/stores",
            "/api/v1/analytics/manager/compare",
            "/api/v1/analytics/platform/summary",
        ]
        for route in forbidden_routes:
            resp = client.get(route, headers=headers)
            assert resp.status_code == 403, f"Expected 403 for {route}, got {resp.status_code}"
            assert "access denied" in resp.json()["detail"].lower()


class TestRBACMultiStoreManager:
    """Verifies Multi-Store Manager access across explicitly assigned stores."""

    def test_manager_access_assigned_tenants(
        self, client: TestClient, setup_rbac_environment
    ):
        """Manager can query analytics for both Store 1 and Store 2."""
        t1 = setup_rbac_environment["t1"]
        t2 = setup_rbac_environment["t2"]
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp1 = client.get(f"/api/v1/analytics/tenants/{t1.id}/summary", headers=headers)
        assert resp1.status_code == 200
        assert resp1.json()["total_orders"] == 100

        resp2 = client.get(f"/api/v1/analytics/tenants/{t2.id}/summary", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["total_orders"] == 50

    def test_manager_access_unassigned_tenant_rejected_403(
        self, client: TestClient, setup_rbac_environment
    ):
        """Manager attempting to access Store 3 (unassigned) is rejected with 403 Forbidden."""
        t3 = setup_rbac_environment["t3"]
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp = client.get(f"/api/v1/analytics/tenants/{t3.id}/summary", headers=headers)
        assert resp.status_code == 403
        assert "not assigned" in resp.json()["detail"].lower()

    def test_manager_combined_summary(
        self, client: TestClient, setup_rbac_environment
    ):
        """GET /api/v1/analytics/manager/summary combines metrics across assigned stores only."""
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp = client.get("/api/v1/analytics/manager/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["assigned_tenants_count"] == 2
        # Store 1 (100 orders) + Store 2 (50 orders) = 150 orders total (Store 3: 30 orders excluded!)
        assert data["total_orders"] == 150

        # Currency separation: Store 1 is USD, Store 2 is EUR -> Root sales MUST BE NULL!
        assert data["currency"] is None
        assert data["gross_sales"] is None
        assert data["net_sales"] is None

        # Verify separate currency breakdowns
        currencies = {c["currency"]: c for c in data["currencies"]}
        assert "USD" in currencies
        assert "EUR" in currencies
        assert "GBP" not in currencies  # Store 3 excluded

        assert Decimal(currencies["USD"]["gross_sales"]) == Decimal("10000.00")
        assert Decimal(currencies["EUR"]["gross_sales"]) == Decimal("6000.00")

    def test_manager_summary_single_currency_filter(
        self, client: TestClient, setup_rbac_environment
    ):
        """Filtering by single currency populates root financial figures."""
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp = client.get("/api/v1/analytics/manager/summary?currency=USD", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["currency"] == "USD"
        assert data["total_orders"] == 100
        assert Decimal(data["gross_sales"]) == Decimal("10000.00")
        assert Decimal(data["net_sales"]) == Decimal("9000.00")
        assert len(data["currencies"]) == 1

    def test_manager_summary_unassigned_store_filter_rejected_403(
        self, client: TestClient, setup_rbac_environment
    ):
        """Manager attempting to filter summary by an unassigned store is rejected with 403."""
        t3 = setup_rbac_environment["t3"]
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp = client.get(f"/api/v1/analytics/manager/summary?tenant_ids={t3.id}", headers=headers)
        assert resp.status_code == 403
        assert "not assigned" in resp.json()["detail"].lower()

    def test_manager_stores_breakdown(
        self, client: TestClient, setup_rbac_environment
    ):
        """GET /api/v1/analytics/manager/stores returns performance rollups for assigned stores."""
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp = client.get("/api/v1/analytics/manager/stores", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_stores"] == 2
        returned_names = [s["tenant_name"] for s in data["stores"]]
        assert "Alpha Store" in returned_names
        assert "Beta Store" in returned_names
        assert "Gamma Store" not in returned_names

    def test_manager_compare_stores(
        self, client: TestClient, setup_rbac_environment
    ):
        """GET /api/v1/analytics/manager/compare returns comparative rankings."""
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp = client.get("/api/v1/analytics/manager/compare", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["compared_stores_count"] == 2
        assert len(data["stores"]) == 2

    def test_manager_empty_assignments(
        self, client: TestClient, setup_rbac_environment
    ):
        """Manager with zero assigned stores receives clean empty summary (200 OK)."""
        token_manager_empty = setup_rbac_environment["token_manager_empty"]
        headers = {"Authorization": f"Bearer {token_manager_empty}"}

        resp = client.get("/api/v1/analytics/manager/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned_tenants_count"] == 0
        assert data["total_orders"] == 0
        assert data["currencies"] == []

        resp_stores = client.get("/api/v1/analytics/manager/stores", headers=headers)
        assert resp_stores.status_code == 200
        assert resp_stores.json()["total_stores"] == 0
        assert resp_stores.json()["stores"] == []

    def test_manager_cannot_access_platform_summary(
        self, client: TestClient, setup_rbac_environment
    ):
        """Store manager attempting to access platform summary receives 403 Forbidden."""
        token_manager = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_manager}"}

        resp = client.get("/api/v1/analytics/platform/summary", headers=headers)
        assert resp.status_code == 403
        assert "platform administrator" in resp.json()["detail"].lower()


class TestRBACPlatformAdministrator:
    """Verifies Platform Administrator access across all stores and platform summary."""

    def test_platform_admin_can_access_any_store(
        self, client: TestClient, setup_rbac_environment
    ):
        """Platform Admin can query analytics for all stores without restriction."""
        t1 = setup_rbac_environment["t1"]
        t2 = setup_rbac_environment["t2"]
        t3 = setup_rbac_environment["t3"]
        token_admin = setup_rbac_environment["token_admin"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        for t in [t1, t2, t3]:
            resp = client.get(f"/api/v1/analytics/tenants/{t.id}/summary", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["tenant_id"] == str(t.id)

    def test_platform_admin_summary(
        self, client: TestClient, setup_rbac_environment
    ):
        """Platform Admin accessing /api/v1/analytics/platform/summary returns platform-wide metrics."""
        token_admin = setup_rbac_environment["token_admin"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        resp = client.get("/api/v1/analytics/platform/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_tenants"] == 3
        # Store 1 (100) + Store 2 (50) + Store 3 (30) = 180 total platform orders
        assert data["total_orders"] == 180

        # Currency separation: Multiple currencies (USD, EUR, GBP) -> Root sales MUST BE NULL!
        assert data["currency"] is None
        assert data["gross_sales"] is None
        assert data["net_sales"] is None

        # Verify separate currency breakdowns
        currencies = {c["currency"]: c for c in data["currencies"]}
        assert "USD" in currencies
        assert "EUR" in currencies
        assert "GBP" in currencies
        assert Decimal(currencies["USD"]["gross_sales"]) == Decimal("10000.00")
        assert Decimal(currencies["EUR"]["gross_sales"]) == Decimal("6000.00")
        assert Decimal(currencies["GBP"]["gross_sales"]) == Decimal("4000.00")

    def test_platform_admin_summary_currency_filter(
        self, client: TestClient, setup_rbac_environment
    ):
        """Platform summary with currency filter populates root figures."""
        token_admin = setup_rbac_environment["token_admin"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        resp = client.get("/api/v1/analytics/platform/summary?currency=GBP", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["currency"] == "GBP"
        assert data["total_orders"] == 30
        assert Decimal(data["gross_sales"]) == Decimal("4000.00")
        assert Decimal(data["net_sales"]) == Decimal("3800.00")
        assert len(data["currencies"]) == 1


class TestRegistrationSecurityAndPrivilegeEscalation:
    """Verifies Priority 1 & 2: Registration security and admin account provisioning."""

    def test_anonymous_cannot_register_or_escalate_privileges(self, client: TestClient):
        """Anonymous public users are rejected from /register to prevent privilege escalation."""
        # Attempt to register
        payload = {
            "email": "hacker@test.com",
            "password": "supersecretpassword123",
            "full_name": "Privilege Escalation Attempt",
        }
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 403
        assert "Public self-registration is disabled" in resp.json()["detail"]

    def test_anonymous_cannot_access_provision_endpoint(self, client: TestClient):
        """Unauthenticated requests to /provision are rejected with 401 Unauthorized."""
        payload = {
            "email": "newuser@test.com",
            "password": "securepassword123",
            "role": "platform_admin",
        }
        resp = client.post("/api/v1/auth/provision", json=payload)
        assert resp.status_code == 401

    def test_tenant_user_cannot_access_provision_endpoint(
        self, client: TestClient, setup_rbac_environment
    ):
        """Tenant users cannot provision accounts (403 Forbidden)."""
        token_t1 = setup_rbac_environment["token_alpha"]
        headers = {"Authorization": f"Bearer {token_t1}"}
        payload = {
            "email": "newuser@test.com",
            "password": "securepassword123",
            "role": "platform_admin",
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 403
        assert "platform administrator privileges required" in resp.json()["detail"]

    def test_manager_cannot_access_provision_endpoint(
        self, client: TestClient, setup_rbac_environment
    ):
        """Store managers cannot provision accounts (403 Forbidden)."""
        token_mgr = setup_rbac_environment["token_manager"]
        headers = {"Authorization": f"Bearer {token_mgr}"}
        payload = {
            "email": "newuser@test.com",
            "password": "securepassword123",
            "role": "store_manager",
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 403
        assert "platform administrator privileges required" in resp.json()["detail"]

    def test_platform_admin_can_provision_tenant_user(
        self, client: TestClient, setup_rbac_environment
    ):
        """Platform administrator can provision a valid tenant_user."""
        token_admin = setup_rbac_environment["token_admin"]
        t1 = setup_rbac_environment["t1"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        payload = {
            "email": "provisioned_tenant_user@test.com",
            "password": "validpassword123",
            "full_name": "Provisioned Staff",
            "role": "tenant_user",
            "tenant_id": str(t1.id),
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "provisioned_tenant_user@test.com"
        assert data["role"] == "tenant_user"
        assert data["tenant_id"] == str(t1.id)
        # Ensure password and hash are not leaked
        assert "password" not in data
        assert "hashed_password" not in data

        # Verify user can log in
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "provisioned_tenant_user@test.com", "password": "validpassword123"},
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()

    def test_platform_admin_can_provision_store_manager_with_assignments(
        self, client: TestClient, setup_rbac_environment
    ):
        """Platform administrator can provision a store_manager with explicit store assignments."""
        token_admin = setup_rbac_environment["token_admin"]
        t1 = setup_rbac_environment["t1"]
        t2 = setup_rbac_environment["t2"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        payload = {
            "email": "provisioned_manager@test.com",
            "password": "validmanagerpass123",
            "full_name": "Regional Manager",
            "role": "store_manager",
            "assigned_tenant_ids": [str(t1.id), str(t2.id)],
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "provisioned_manager@test.com"
        assert data["role"] == "store_manager"
        assert set(data["assigned_tenant_ids"]) == {str(t1.id), str(t2.id)}

        # Verify manager can log in and assigned_tenant_ids are returned
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "provisioned_manager@test.com", "password": "validmanagerpass123"},
        )
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert set(login_data["assigned_tenant_ids"]) == {str(t1.id), str(t2.id)}

    def test_provision_tenant_user_requires_tenant_id(
        self, client: TestClient, setup_rbac_environment
    ):
        """Provisioning tenant_user without tenant_id returns 400 Bad Request."""
        token_admin = setup_rbac_environment["token_admin"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        payload = {
            "email": "orphan_user@test.com",
            "password": "validpassword123",
            "role": "tenant_user",
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "tenant_id is required" in resp.json()["detail"]

    def test_provision_tenant_user_nonexistent_tenant_rejected(
        self, client: TestClient, setup_rbac_environment
    ):
        """Provisioning tenant_user with non-existent tenant_id returns 400 Bad Request."""
        token_admin = setup_rbac_environment["token_admin"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        fake_id = str(uuid.uuid4())
        payload = {
            "email": "bad_tenant_user@test.com",
            "password": "validpassword123",
            "role": "tenant_user",
            "tenant_id": fake_id,
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 400
        assert f"Target tenant '{fake_id}' does not exist" in resp.json()["detail"]

    def test_provision_tenant_user_cannot_have_manager_assignments(
        self, client: TestClient, setup_rbac_environment
    ):
        """Provisioning tenant_user with assigned_tenant_ids returns 400 Bad Request."""
        token_admin = setup_rbac_environment["token_admin"]
        t1 = setup_rbac_environment["t1"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        payload = {
            "email": "hybrid_user@test.com",
            "password": "validpassword123",
            "role": "tenant_user",
            "tenant_id": str(t1.id),
            "assigned_tenant_ids": [str(t1.id)],
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "assigned_tenant_ids cannot be specified for tenant_user role" in resp.json()["detail"]

    def test_provision_manager_cannot_have_home_tenant_id(
        self, client: TestClient, setup_rbac_environment
    ):
        """Provisioning store_manager with tenant_id returns 400 Bad Request."""
        token_admin = setup_rbac_environment["token_admin"]
        t1 = setup_rbac_environment["t1"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        payload = {
            "email": "bad_manager@test.com",
            "password": "validpassword123",
            "role": "store_manager",
            "tenant_id": str(t1.id),
            "assigned_tenant_ids": [str(t1.id)],
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "tenant_id cannot be specified for store_manager role" in resp.json()["detail"]

    def test_provision_manager_nonexistent_store_assignment_rejected(
        self, client: TestClient, setup_rbac_environment
    ):
        """Provisioning store_manager with a non-existent store returns 400 Bad Request."""
        token_admin = setup_rbac_environment["token_admin"]
        fake_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {token_admin}"}

        payload = {
            "email": "ghost_store_manager@test.com",
            "password": "validpassword123",
            "role": "store_manager",
            "assigned_tenant_ids": [fake_id],
        }
        resp = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp.status_code == 400
        assert f"Assigned tenant '{fake_id}' does not exist" in resp.json()["detail"]

    def test_provision_platform_admin_cannot_have_tenant_associations(
        self, client: TestClient, setup_rbac_environment
    ):
        """Platform admins cannot be bound to specific home tenants or assigned stores."""
        token_admin = setup_rbac_environment["token_admin"]
        t1 = setup_rbac_environment["t1"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        # Test with tenant_id
        resp1 = client.post(
            "/api/v1/auth/provision",
            json={"email": "admin1@test.com", "password": "pass12345678", "role": "platform_admin", "tenant_id": str(t1.id)},
            headers=headers,
        )
        assert resp1.status_code == 400

        # Test with assigned_tenant_ids
        resp2 = client.post(
            "/api/v1/auth/provision",
            json={"email": "admin2@test.com", "password": "pass12345678", "role": "platform_admin", "assigned_tenant_ids": [str(t1.id)]},
            headers=headers,
        )
        assert resp2.status_code == 400

    def test_provision_duplicate_email_rejected(
        self, client: TestClient, setup_rbac_environment
    ):
        """Attempting to provision a user with an already registered email returns 400 Bad Request."""
        token_admin = setup_rbac_environment["token_admin"]
        t1 = setup_rbac_environment["t1"]
        headers = {"Authorization": f"Bearer {token_admin}"}

        payload = {
            "email": "existing_user@test.com",
            "password": "password123456",
            "role": "tenant_user",
            "tenant_id": str(t1.id),
        }
        # First creation succeeds
        resp1 = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp1.status_code == 201

        # Duplicate creation fails
        resp2 = client.post("/api/v1/auth/provision", json=payload, headers=headers)
        assert resp2.status_code == 400
        assert "already exists" in resp2.json()["detail"]


class TestDatabaseRoleAndAssignmentIntegrity:
    """Verifies Priority 6: Relational constraints prevent assigning non-managers to stores."""

    def test_database_blocks_assignment_to_tenant_user(
        self, rbac_session: Session, setup_rbac_environment
    ):
        """Database composite foreign key rejects assigning a store to a tenant_user."""
        t1 = setup_rbac_environment["t1"]
        tenant_user = setup_rbac_environment["user_alpha"]

        # Attempt to insert a store assignment for a user whose role is 'tenant_user'
        assignment = ManagerTenantAssignment(
            id=uuid.uuid4(),
            user_id=tenant_user.id,
            user_role="store_manager",  # check constraint passes, but FK to users(id, role) fails!
            tenant_id=t1.id,
        )
        rbac_session.add(assignment)
        with pytest.raises(sa.exc.IntegrityError):
            rbac_session.commit()
        rbac_session.rollback()

    def test_database_blocks_duplicate_assignment(
        self, rbac_session: Session, setup_rbac_environment
    ):
        """Database unique constraint rejects duplicate (user_id, tenant_id) mappings."""
        t1 = setup_rbac_environment["t1"]
        manager = setup_rbac_environment["manager_1_2"]

        # manager is already assigned to t1 in setup_rbac_environment
        duplicate = ManagerTenantAssignment(
            id=uuid.uuid4(),
            user_id=manager.id,
            user_role="store_manager",
            tenant_id=t1.id,
        )
        rbac_session.add(duplicate)
        with pytest.raises(sa.exc.IntegrityError):
            rbac_session.commit()
        rbac_session.rollback()

    def test_database_blocks_changing_manager_role_with_existing_assignments(
        self, rbac_session: Session, setup_rbac_environment
    ):
        """Relational constraint prevents downgrading a manager to tenant_user while assignments exist."""
        manager = setup_rbac_environment["manager_1_2"]

        # manager has active assignments to t1 and t2
        manager.role = UserRole.TENANT_USER.value
        with pytest.raises(sa.exc.IntegrityError):
            rbac_session.commit()
        rbac_session.rollback()


class TestJWTCryptographicSecurityAndConfiguration:
    """Verifies Priority 3: JWT secrets cannot be empty, short, or insecure defaults."""

    def test_jwt_secret_rejects_empty(self):
        """Settings fails immediately if JWT_SECRET_KEY is empty."""
        with pytest.raises(ValueError, match="JWT_SECRET_KEY must be provided"):
            Settings(JWT_SECRET_KEY="")

    def test_jwt_secret_rejects_short(self):
        """Settings fails immediately if JWT_SECRET_KEY is under 32 characters."""
        with pytest.raises(ValueError, match="at least 32 characters long"):
            Settings(JWT_SECRET_KEY="short-secret-key-16-bytes")

    def test_jwt_secret_rejects_known_defaults(self):
        """Settings rejects known hardcoded placeholder default strings."""
        with pytest.raises(ValueError, match="known default, placeholder, or insecure"):
            Settings(JWT_SECRET_KEY="aggrix-super-secret-cryptographic-jwt-signing-key-32-bytes-min")


class TestCORSSecurityConfiguration:
    """Verifies Priority 4: CORS forbids wildcards and restricts allowed origins."""

    def test_cors_rejects_wildcard_origin(self):
        """Configuring wildcard '*' in BACKEND_CORS_ORIGINS is strictly rejected."""
        with pytest.raises(ValueError, match="CORS wildcard '\\*' origin is strictly forbidden"):
            Settings(
                JWT_SECRET_KEY="valid-secret-key-with-over-32-characters-test",
                BACKEND_CORS_ORIGINS="*",
            )

    def test_untrusted_cors_origin_not_reflected(self, client: TestClient):
        """CORS middleware does not reflect untrusted origins."""
        untrusted_headers = {
            "Origin": "http://evil-attacker-site.com",
            "Access-Control-Request-Method": "GET",
        }
        resp = client.options("/api/v1/health", headers=untrusted_headers)
        # Access-Control-Allow-Origin must NOT equal the untrusted origin
        assert resp.headers.get("access-control-allow-origin") != "http://evil-attacker-site.com"

    def test_trusted_cors_origin_allowed(self, client: TestClient):
        """Explicitly configured trusted origins receive CORS allow headers."""
        trusted_headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
        resp = client.options("/api/v1/health", headers=trusted_headers)
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestCredentialLeakageAndTimingMitigation:
    """Verifies Priority 5: Constant-time dummy verification and zero credential leakage."""

    def test_login_unknown_email_and_bad_password_produce_identical_errors(
        self, client: TestClient, setup_rbac_environment
    ):
        """Unknown email and bad password return identical generic error messages (no enumeration)."""
        resp_bad_email = client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent_email_12345@test.com", "password": "anypassword"},
        )
        assert resp_bad_email.status_code == 401
        assert resp_bad_email.json()["detail"] == "Invalid email or password."

        resp_bad_pass = client.post(
            "/api/v1/auth/login",
            json={"email": "user.alpha@store.test", "password": "wrongpassword"},
        )
        assert resp_bad_pass.status_code == 401
        assert resp_bad_pass.json()["detail"] == "Invalid email or password."

    def test_password_and_hash_never_exposed_in_api_responses(
        self, client: TestClient, setup_rbac_environment
    ):
        """API endpoints (/login, /me, /provision) never leak plaintext passwords or hashes."""
        # 1. Login response
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "user.alpha@store.test", "password": "ValidPassword123!"},
        )
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert "password" not in login_data
        assert "hashed_password" not in login_data

        token = login_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. /me profile response
        me_resp = client.get("/api/v1/auth/me", headers=headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert "password" not in me_data
        assert "hashed_password" not in me_data


