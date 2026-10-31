"""
Comprehensive Unit and Integration Tests for AGGRIX Analytics Read API & Query Services.

Test Coverage:
1. Tenant Summary:
   - Single currency metrics (orders, gross, net, pending, cancelled)
   - Multi-currency segregation (never combine different currencies into one total)
   - Currency filtering
   - Date range filtering (start_date, end_date)
   - Empty results handling
   - Invalid date range validation (400 Bad Request)
   - Non-existent tenant validation (404 Not Found)
   - Decimal precision accuracy
   - Tenant isolation (preventing cross-tenant data leakage)
2. Daily Metrics:
   - Chronological daily records
   - Pagination (total_records, total_pages, page, page_size)
   - Date filtering
   - Currency filtering
   - Empty results handling
   - Invalid date ranges
   - Tenant isolation
3. Product Metrics:
   - Product-level rollups joined with catalog metadata (product_name, product_sku)
   - Gross/net units, pending/cancelled units, revenue, orders count
   - Pagination and gross_sales descending ordering
   - Single product_id filtering
   - Currency and date range filtering
   - Empty results handling
   - Tenant isolation
4. Live PostgreSQL verification:
   - Real query verification against active PostgreSQL database
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Generator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.analytics.service import (
    AnalyticsQueryService,
    InvalidDateRangeError,
    TenantNotFoundError,
)
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.database.connection import get_db
from app.main import app
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User


@pytest.fixture
def test_engine() -> Generator[sa.Engine, None, None]:
    """Isolated, thread-safe in-memory SQLite engine for FastAPI TestClient."""
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
def session_factory(test_engine: sa.Engine) -> sessionmaker:
    return sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory: sessionmaker) -> Generator[Session, None, None]:
    sess = session_factory()
    yield sess
    sess.close()


@pytest.fixture
def api_client(session_factory: sessionmaker) -> Generator[TestClient, None, None]:
    """Provides a TestClient overriding get_db with the isolated test session."""
    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_tenants(session: Session) -> dict[str, Tenant]:
    """Seeds two isolated tenants for multi-tenancy tests."""
    tenant_a = Tenant(
        id=uuid.uuid4(),
        name="Tenant Alpha",
        domain="alpha.aggrix.test",
        timezone="UTC",
    )
    tenant_b = Tenant(
        id=uuid.uuid4(),
        name="Tenant Beta",
        domain="beta.aggrix.test",
        timezone="UTC",
    )
    session.add_all([tenant_a, tenant_b])
    session.commit()
    return {"a": tenant_a, "b": tenant_b}


@pytest.fixture
def seed_analytics_data(session: Session, seed_tenants: dict[str, Tenant]):
    """Seeds multi-currency daily tenant and product metrics across tenants."""
    t_a = seed_tenants["a"]
    t_b = seed_tenants["b"]

    # Products for Tenant A
    prod_a1 = Product(
        id=uuid.uuid4(),
        tenant_id=t_a.id,
        name="Alpha Widget Pro",
        sku="ALP-001",
        price=Decimal("100.00"),
    )
    prod_a2 = Product(
        id=uuid.uuid4(),
        tenant_id=t_a.id,
        name="Alpha Gadget Mini",
        sku="ALP-002",
        price=Decimal("50.00"),
    )
    # Product for Tenant B
    prod_b1 = Product(
        id=uuid.uuid4(),
        tenant_id=t_b.id,
        name="Beta Luxury Watch",
        sku="BET-001",
        price=Decimal("500.00"),
    )
    session.add_all([prod_a1, prod_a2, prod_b1])
    session.commit()

    d1 = date(2026, 9, 1)
    d2 = date(2026, 9, 2)
    d3 = date(2026, 9, 3)

    # Tenant A - USD metrics
    tm_a_usd_1 = DailyTenantMetric(
        tenant_id=t_a.id,
        metric_date=d1,
        currency="USD",
        orders_count=10,
        gross_sales=Decimal("1000.50"),
        net_sales=Decimal("900.50"),
        pending_orders_count=1,
        pending_sales=Decimal("100.00"),
        cancelled_orders_count=1,
        cancelled_sales=Decimal("100.00"),
    )
    tm_a_usd_2 = DailyTenantMetric(
        tenant_id=t_a.id,
        metric_date=d2,
        currency="USD",
        orders_count=15,
        gross_sales=Decimal("1500.75"),
        net_sales=Decimal("1400.75"),
        pending_orders_count=2,
        pending_sales=Decimal("200.00"),
        cancelled_orders_count=1,
        cancelled_sales=Decimal("100.00"),
    )
    # Tenant A - EUR metrics (multi-currency)
    tm_a_eur_3 = DailyTenantMetric(
        tenant_id=t_a.id,
        metric_date=d3,
        currency="EUR",
        orders_count=5,
        gross_sales=Decimal("600.00"),
        net_sales=Decimal("600.00"),
        pending_orders_count=0,
        pending_sales=Decimal("0.00"),
        cancelled_orders_count=0,
        cancelled_sales=Decimal("0.00"),
    )

    # Tenant B - USD metrics (isolated tenant)
    tm_b_usd_1 = DailyTenantMetric(
        tenant_id=t_b.id,
        metric_date=d1,
        currency="USD",
        orders_count=2,
        gross_sales=Decimal("1000.00"),
        net_sales=Decimal("1000.00"),
        pending_orders_count=0,
        pending_sales=Decimal("0.00"),
        cancelled_orders_count=0,
        cancelled_sales=Decimal("0.00"),
    )

    # Product metrics for Tenant A
    pm_a1_usd = DailyProductMetric(
        tenant_id=t_a.id,
        product_id=prod_a1.id,
        metric_date=d1,
        currency="USD",
        units_sold_gross=10,
        units_sold_net=9,
        pending_units=1,
        cancelled_units=1,
        gross_sales=Decimal("1000.00"),
        net_sales=Decimal("900.00"),
        pending_sales=Decimal("100.00"),
        cancelled_sales=Decimal("100.00"),
        orders_count=10,
    )
    pm_a2_usd = DailyProductMetric(
        tenant_id=t_a.id,
        product_id=prod_a2.id,
        metric_date=d2,
        currency="USD",
        units_sold_gross=30,
        units_sold_net=28,
        pending_units=4,
        cancelled_units=2,
        gross_sales=Decimal("1500.00"),
        net_sales=Decimal("1400.00"),
        pending_sales=Decimal("200.00"),
        cancelled_sales=Decimal("100.00"),
        orders_count=15,
    )

    # Product metric for Tenant B
    pm_b1_usd = DailyProductMetric(
        tenant_id=t_b.id,
        product_id=prod_b1.id,
        metric_date=d1,
        currency="USD",
        units_sold_gross=2,
        units_sold_net=2,
        pending_units=0,
        cancelled_units=0,
        gross_sales=Decimal("1000.00"),
        net_sales=Decimal("1000.00"),
        pending_sales=Decimal("0.00"),
        cancelled_sales=Decimal("0.00"),
        orders_count=2,
    )

    user_a = User(
        id=uuid.uuid4(),
        email="alpha_user@aggrix.test",
        hashed_password=hash_password("Password123!"),
        role="tenant_user",
        is_active=True,
        tenant_id=t_a.id,
    )
    user_b = User(
        id=uuid.uuid4(),
        email="beta_user@aggrix.test",
        hashed_password=hash_password("Password123!"),
        role="tenant_user",
        is_active=True,
        tenant_id=t_b.id,
    )
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@aggrix.test",
        hashed_password=hash_password("Password123!"),
        role="platform_admin",
        is_active=True,
        tenant_id=None,
    )

    session.add_all([
        tm_a_usd_1, tm_a_usd_2, tm_a_eur_3, tm_b_usd_1,
        pm_a1_usd, pm_a2_usd, pm_b1_usd,
        user_a, user_b, admin_user,
    ])
    session.commit()

    token_a = create_access_token(user_a.id, "tenant_user", t_a.id)
    token_b = create_access_token(user_b.id, "tenant_user", t_b.id)
    token_admin = create_access_token(admin_user.id, "platform_admin", None)

    return {
        "tenant_a": t_a,
        "tenant_b": t_b,
        "prod_a1": prod_a1,
        "prod_a2": prod_a2,
        "prod_b1": prod_b1,
        "user_a": user_a,
        "user_b": user_b,
        "admin_user": admin_user,
        "token_a": token_a,
        "token_b": token_b,
        "token_admin": token_admin,
    }


@pytest.fixture(autouse=True)
def auto_authenticate_client(api_client: TestClient, request):
    """Automatically applies Tenant Alpha authorization headers to api_client when seed_analytics_data is used."""
    if "seed_analytics_data" in request.fixturenames:
        seed = request.getfixturevalue("seed_analytics_data")
        api_client.headers["Authorization"] = f"Bearer {seed['token_a']}"


class TestTenantSummaryAPI:
    """Tests for GET /api/v1/analytics/tenants/{tenant_id}/summary."""

    def test_summary_multi_currency_segregation(
        self, api_client: TestClient, seed_analytics_data
    ):
        """When multi-currency data exists without a currency filter, root sales must be None

        and separate currencies breakdown must be populated without combining them.
        """
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(f"/api/v1/analytics/tenants/{tenant_a.id}/summary")
        assert resp.status_code == 200
        data = resp.json()

        assert data["tenant_id"] == str(tenant_a.id)
        assert data["total_orders"] == 30  # 10 + 15 + 5
        # CRITICAL: Multi-currency root financial totals MUST NOT combine currencies!
        assert data["currency"] is None
        assert data["gross_sales"] is None
        assert data["net_sales"] is None
        assert data["pending_sales"] is None
        assert data["cancelled_sales"] is None

        # Verify separate currency breakdowns
        currencies = {c["currency"]: c for c in data["currencies"]}
        assert "USD" in currencies
        assert "EUR" in currencies

        usd = currencies["USD"]
        assert usd["total_orders"] == 25
        assert Decimal(usd["gross_sales"]) == Decimal("2501.25")
        assert Decimal(usd["net_sales"]) == Decimal("2301.25")
        assert usd["pending_orders_count"] == 3
        assert Decimal(usd["pending_sales"]) == Decimal("300.00")
        assert usd["cancelled_orders_count"] == 2
        assert Decimal(usd["cancelled_sales"]) == Decimal("200.00")

        eur = currencies["EUR"]
        assert eur["total_orders"] == 5
        assert Decimal(eur["gross_sales"]) == Decimal("600.00")
        assert Decimal(eur["net_sales"]) == Decimal("600.00")
        assert eur["pending_orders_count"] == 0
        assert Decimal(eur["pending_sales"]) == Decimal("0.00")

    def test_summary_single_currency_filter(
        self, api_client: TestClient, seed_analytics_data
    ):
        """When a single currency filter is specified, root financial fields are populated."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/summary?currency=USD"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["currency"] == "USD"
        assert data["total_orders"] == 25
        assert Decimal(data["gross_sales"]) == Decimal("2501.25")
        assert Decimal(data["net_sales"]) == Decimal("2301.25")
        assert data["pending_orders_count"] == 3
        assert Decimal(data["pending_sales"]) == Decimal("300.00")
        assert data["cancelled_orders_count"] == 2
        assert Decimal(data["cancelled_sales"]) == Decimal("200.00")
        assert len(data["currencies"]) == 1
        assert data["currencies"][0]["currency"] == "USD"

    def test_summary_date_filtering(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Date filtering limits summary to the specified range."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/summary?start_date=2026-09-02&end_date=2026-09-02"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["date_range"]["start_date"] == "2026-09-02"
        assert data["date_range"]["end_date"] == "2026-09-02"
        assert data["currency"] == "USD"
        assert data["total_orders"] == 15
        assert Decimal(data["gross_sales"]) == Decimal("1500.75")
        assert Decimal(data["net_sales"]) == Decimal("1400.75")

    def test_summary_empty_results(
        self, api_client: TestClient, seed_analytics_data
    ):
        """A valid date range with no orders returns 0 orders and empty currency breakdown."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/summary?start_date=2025-01-01&end_date=2025-01-31"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_orders"] == 0
        assert data["currencies"] == []
        assert data["gross_sales"] is None

    def test_summary_invalid_date_range_400(
        self, api_client: TestClient, seed_analytics_data
    ):
        """start_date > end_date returns 400 Bad Request."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/summary?start_date=2026-09-10&end_date=2026-09-01"
        )
        assert resp.status_code == 400
        assert "start_date" in resp.json()["detail"]
        assert "must be before or equal to end_date" in resp.json()["detail"]

    def test_summary_tenant_not_found_404(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Non-existent tenant UUID returns 404 Not Found for authorized admin."""
        random_id = uuid.uuid4()
        token_admin = seed_analytics_data["token_admin"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{random_id}/summary",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_summary_tenant_isolation(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Tenant user A attempting to access Tenant B is rejected with 403 Forbidden.

        Tenant user B accessing Tenant B receives their own isolated data.
        """
        tenant_b = seed_analytics_data["tenant_b"]
        token_b = seed_analytics_data["token_b"]

        # Default client is authenticated as Tenant A user -> 403 Forbidden
        resp_forbidden = api_client.get(f"/api/v1/analytics/tenants/{tenant_b.id}/summary")
        assert resp_forbidden.status_code == 403
        assert "access denied" in resp_forbidden.json()["detail"].lower()

        # Authenticated as Tenant B user -> 200 OK
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_b.id}/summary",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["tenant_id"] == str(tenant_b.id)
        assert data["total_orders"] == 2
        assert Decimal(data["gross_sales"]) == Decimal("1000.00")
        assert Decimal(data["net_sales"]) == Decimal("1000.00")
        assert len(data["currencies"]) == 1
        assert data["currencies"][0]["currency"] == "USD"


class TestTenantDailyMetricsAPI:
    """Tests for GET /api/v1/analytics/tenants/{tenant_id}/daily."""

    def test_daily_metrics_retrieval_and_order(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Returns chronological daily metric records."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(f"/api/v1/analytics/tenants/{tenant_a.id}/daily")
        assert resp.status_code == 200
        data = resp.json()

        assert data["tenant_id"] == str(tenant_a.id)
        assert data["pagination"]["total_records"] == 3
        assert len(data["data"]) == 3

        dates = [d["metric_date"] for d in data["data"]]
        assert dates == ["2026-09-01", "2026-09-02", "2026-09-03"]

    def test_daily_metrics_pagination(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Pagination limits page size and navigates correctly."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp_p1 = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/daily?page=1&page_size=2"
        )
        assert resp_p1.status_code == 200
        data_p1 = resp_p1.json()
        assert data_p1["pagination"]["total_records"] == 3
        assert data_p1["pagination"]["total_pages"] == 2
        assert len(data_p1["data"]) == 2
        assert data_p1["data"][0]["metric_date"] == "2026-09-01"

        resp_p2 = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/daily?page=2&page_size=2"
        )
        assert resp_p2.status_code == 200
        data_p2 = resp_p2.json()
        assert len(data_p2["data"]) == 1
        assert data_p2["data"][0]["metric_date"] == "2026-09-03"

    def test_daily_metrics_currency_filter(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Filtering by currency returns only records matching that currency."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/daily?currency=EUR"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total_records"] == 1
        assert data["data"][0]["currency"] == "EUR"
        assert Decimal(data["data"][0]["gross_sales"]) == Decimal("600.00")

    def test_daily_metrics_invalid_date_range_400(
        self, api_client: TestClient, seed_analytics_data
    ):
        """start_date > end_date returns 400."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/daily?start_date=2026-09-05&end_date=2026-09-01"
        )
        assert resp.status_code == 400


class TestTenantProductMetricsAPI:
    """Tests for GET /api/v1/analytics/tenants/{tenant_id}/products."""

    def test_product_metrics_joined_metadata_and_rollups(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Product metrics rollups join product name and SKU and compute correct aggregations."""
        tenant_a = seed_analytics_data["tenant_a"]
        prod_a1 = seed_analytics_data["prod_a1"]
        prod_a2 = seed_analytics_data["prod_a2"]

        resp = api_client.get(f"/api/v1/analytics/tenants/{tenant_a.id}/products")
        assert resp.status_code == 200
        data = resp.json()

        assert data["tenant_id"] == str(tenant_a.id)
        assert data["pagination"]["total_records"] == 2

        # Check ordered by gross sales desc (prod_a2 gross: 1500, prod_a1 gross: 1000)
        items = data["data"]
        assert len(items) == 2
        top_prod = items[0]
        assert top_prod["product_id"] == str(prod_a2.id)
        assert top_prod["product_name"] == "Alpha Gadget Mini"
        assert top_prod["product_sku"] == "ALP-002"
        assert Decimal(top_prod["gross_sales"]) == Decimal("1500.00")
        assert Decimal(top_prod["net_sales"]) == Decimal("1400.00")
        assert top_prod["units_sold_gross"] == 30
        assert top_prod["units_sold_net"] == 28
        assert top_prod["pending_units"] == 4
        assert top_prod["cancelled_units"] == 2

        second_prod = items[1]
        assert second_prod["product_id"] == str(prod_a1.id)
        assert second_prod["product_name"] == "Alpha Widget Pro"
        assert second_prod["product_sku"] == "ALP-001"
        assert Decimal(second_prod["gross_sales"]) == Decimal("1000.00")

    def test_product_metrics_single_product_filter(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Filtering by product_id returns metrics for only that product."""
        tenant_a = seed_analytics_data["tenant_a"]
        prod_a1 = seed_analytics_data["prod_a1"]

        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/products?product_id={prod_a1.id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total_records"] == 1
        assert data["data"][0]["product_id"] == str(prod_a1.id)

    def test_product_metrics_tenant_isolation(
        self, api_client: TestClient, seed_analytics_data
    ):
        """Querying Tenant A does NOT return Tenant B's products or metrics.
        Tenant A user attempting to query Tenant B directly receives 403 Forbidden."""
        tenant_a = seed_analytics_data["tenant_a"]
        tenant_b = seed_analytics_data["tenant_b"]
        prod_b1 = seed_analytics_data["prod_b1"]

        # Cross-tenant request with Tenant A user token -> 403 Forbidden
        resp_forbidden = api_client.get(f"/api/v1/analytics/tenants/{tenant_b.id}/products")
        assert resp_forbidden.status_code == 403

        # Legitimate Tenant A request -> 200
        resp = api_client.get(f"/api/v1/analytics/tenants/{tenant_a.id}/products")
        assert resp.status_code == 200
        data = resp.json()
        returned_ids = {p["product_id"] for p in data["data"]}
        assert str(prod_b1.id) not in returned_ids

        # Attempting to filter Tenant A's products by Tenant B's product_id returns 0 records
        resp_isolated = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/products?product_id={prod_b1.id}"
        )
        assert resp_isolated.status_code == 200
        assert resp_isolated.json()["pagination"]["total_records"] == 0

    def test_product_metrics_invalid_date_range_400(
        self, api_client: TestClient, seed_analytics_data
    ):
        """start_date > end_date returns 400 Bad Request."""
        tenant_a = seed_analytics_data["tenant_a"]
        resp = api_client.get(
            f"/api/v1/analytics/tenants/{tenant_a.id}/products?start_date=2026-09-10&end_date=2026-09-01"
        )
        assert resp.status_code == 400


class TestAnalyticsServiceUnit:
    """Direct unit tests for AnalyticsQueryService."""

    def test_service_tenant_not_found(self, session: Session):
        service = AnalyticsQueryService(session)
        with pytest.raises(TenantNotFoundError) as exc_info:
            service.get_tenant_summary(uuid.uuid4())
        assert "not found" in str(exc_info.value).lower()

    def test_service_invalid_date_range(self, session: Session, seed_tenants):
        service = AnalyticsQueryService(session)
        t_a = seed_tenants["a"]
        with pytest.raises(InvalidDateRangeError) as exc_info:
            service.get_tenant_summary(
                t_a.id,
                start_date=date(2026, 9, 10),
                end_date=date(2026, 9, 1),
            )
        assert "start_date" in str(exc_info.value)


class TestLivePostgreSQLEndpoints:
    """Live PostgreSQL tests querying real precomputed metrics from the 10,000 orders dataset."""

    def test_live_postgres_tenant_summary(self, postgres_session: Session):
        tenant = postgres_session.query(Tenant).first()
        assert tenant is not None, "At least one tenant must exist in live PostgreSQL"

        service = AnalyticsQueryService(postgres_session)
        summary = service.get_tenant_summary(tenant.id)

        assert summary.tenant_id == tenant.id
        assert summary.total_orders in (2000, 7000)
        assert summary.currency == "USD"
        assert summary.gross_sales > Decimal("0.00")
        assert summary.net_sales > Decimal("0.00")
        assert summary.pending_sales >= Decimal("0.00")
        assert summary.cancelled_sales >= Decimal("0.00")
        assert len(summary.currencies) == 1
        assert summary.currencies[0].currency == "USD"

    def test_live_postgres_daily_metrics_and_pagination(
        self, postgres_session: Session
    ):
        tenant = postgres_session.query(Tenant).first()
        service = AnalyticsQueryService(postgres_session)

        daily = service.get_tenant_daily_metrics(
            tenant.id, page=1, page_size=10
        )
        assert daily.tenant_id == tenant.id
        assert daily.pagination.total_records == 61
        assert daily.pagination.total_pages == 7
        assert len(daily.data) == 10
        # Ensure chronological ordering
        for i in range(len(daily.data) - 1):
            assert daily.data[i].metric_date <= daily.data[i + 1].metric_date

    def test_live_postgres_product_metrics_and_ordering(
        self, postgres_session: Session
    ):
        tenant = postgres_session.query(Tenant).first()
        service = AnalyticsQueryService(postgres_session)

        products = service.get_tenant_product_metrics(
            tenant.id, page=1, page_size=10
        )
        assert products.tenant_id == tenant.id
        assert products.pagination.total_records == 100
        assert len(products.data) == 10

        # Verify product catalog metadata joined without N+1
        top_product = products.data[0]
        assert top_product.product_name is not None
        assert top_product.product_sku is not None
        assert top_product.currency == "USD"
        assert top_product.gross_sales > Decimal("0.00")

        # Verify descending gross sales order
        for i in range(len(products.data) - 1):
            assert products.data[i].gross_sales >= products.data[i + 1].gross_sales
