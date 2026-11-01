"""
AGGRIX Analytics Query Service Layer.

Encapsulates read-only analytical query operations retrieving precomputed
metrics from daily_tenant_metrics and daily_product_metrics.

Key Architectural Guarantees:
1. Queries precomputed summary rollups only — never raw orders or line items.
2. Tenant scoping is strictly enforced at every query boundary.
3. Pure SQLAlchemy 2.0 constructs with explicit aggregation.
4. Preserves exact Decimal monetary values across all aggregation operations.
5. Multi-currency values are strictly segregated and never summed together.
6. Eliminates N+1 query patterns through joined aggregation.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.analytics import (
    CurrencySummary,
    DailyMetricRecord,
    DateRangeFilter,
    OrderStatusDistributionResponse,
    OrderStatusMetric,
    PaginationMeta,
    ProductMetricRecord,
    RecentOrderRecord,
    RecentOrdersResponse,
    TenantDailyMetricsResponse,
    TenantListItem,
    TenantListResponse,
    TenantOverviewResponse,
    TenantProductMetricsResponse,
    TenantSummaryResponse,
)
from app.schemas.manager import (
    ManagerCompareResponse,
    ManagerStoresResponse,
    ManagerSummaryResponse,
    PlatformSummaryResponse,
    StorePerformanceRecord,
)


class TenantNotFoundError(Exception):
    """Raised when a requested tenant does not exist in the database."""

    def __init__(self, tenant_id: uuid.UUID):
        self.tenant_id = tenant_id
        super().__init__(f"Tenant with ID '{tenant_id}' not found.")


class InvalidDateRangeError(Exception):
    """Raised when query date filter bounds are logically invalid."""

    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        super().__init__(
            f"Invalid date range: start_date ({start_date}) must be before or equal to end_date ({end_date})."
        )


class AnalyticsQueryService:
    """
    Read-only query service executing analytical aggregations against
    precomputed tenant and product summary tables.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _verify_tenant_exists(self, tenant_id: uuid.UUID) -> Tenant:
        """Verifies that the target tenant exists. Raises TenantNotFoundError if not found."""
        tenant = self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        ).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundError(tenant_id)
        return tenant

    def _validate_date_range(
        self, start_date: Optional[date], end_date: Optional[date]
    ) -> None:
        """Validates that start_date <= end_date if both are supplied."""
        if start_date is not None and end_date is not None:
            if start_date > end_date:
                raise InvalidDateRangeError(start_date, end_date)

    def get_tenant_summary(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
    ) -> TenantSummaryResponse:
        """
        Retrieves precomputed tenant-level performance summaries.

        Financial values are segregated by currency. If multiple currencies are present
        without a single-currency filter, root-level sales figures are set to None
        and exact figures are returned in the 'currencies' breakdown list.
        """
        self._verify_tenant_exists(tenant_id)
        self._validate_date_range(start_date, end_date)

        target_currency = currency.upper().strip() if currency else None

        stmt = (
            select(
                DailyTenantMetric.currency,
                func.coalesce(func.sum(DailyTenantMetric.orders_count), 0).label("total_orders"),
                func.coalesce(func.sum(DailyTenantMetric.gross_sales), Decimal("0.00")).label("gross_sales"),
                func.coalesce(func.sum(DailyTenantMetric.net_sales), Decimal("0.00")).label("net_sales"),
                func.coalesce(func.sum(DailyTenantMetric.pending_orders_count), 0).label("pending_orders_count"),
                func.coalesce(func.sum(DailyTenantMetric.pending_sales), Decimal("0.00")).label("pending_sales"),
                func.coalesce(func.sum(DailyTenantMetric.cancelled_orders_count), 0).label("cancelled_orders_count"),
                func.coalesce(func.sum(DailyTenantMetric.cancelled_sales), Decimal("0.00")).label("cancelled_sales"),
            )
            .where(DailyTenantMetric.tenant_id == tenant_id)
        )

        if start_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date <= end_date)
        if target_currency:
            stmt = stmt.where(DailyTenantMetric.currency == target_currency)

        stmt = stmt.group_by(DailyTenantMetric.currency).order_by(DailyTenantMetric.currency.asc())
        rows = self.session.execute(stmt).all()

        currencies: List[CurrencySummary] = []
        total_orders_all = 0

        for r in rows:
            orders_cnt = int(r.total_orders)
            gross = Decimal(str(r.gross_sales))
            aov = (gross / orders_cnt).quantize(Decimal("0.01")) if orders_cnt > 0 else Decimal("0.00")
            curr_summary = CurrencySummary(
                currency=r.currency,
                total_orders=orders_cnt,
                gross_sales=gross,
                net_sales=Decimal(str(r.net_sales)),
                pending_orders_count=int(r.pending_orders_count),
                pending_sales=Decimal(str(r.pending_sales)),
                cancelled_orders_count=int(r.cancelled_orders_count),
                cancelled_sales=Decimal(str(r.cancelled_sales)),
                average_order_value=aov,
            )
            currencies.append(curr_summary)
            total_orders_all += orders_cnt

        date_filter = DateRangeFilter(start_date=start_date, end_date=end_date)
        active_customers = self.get_active_customers_count(tenant_id, start_date=start_date, end_date=end_date)

        # Single currency requested or exactly one currency present in data
        if len(currencies) == 1:
            single = currencies[0]
            return TenantSummaryResponse(
                tenant_id=tenant_id,
                date_range=date_filter,
                currency=single.currency,
                total_orders=single.total_orders,
                gross_sales=single.gross_sales,
                net_sales=single.net_sales,
                pending_orders_count=single.pending_orders_count,
                pending_sales=single.pending_sales,
                cancelled_orders_count=single.cancelled_orders_count,
                cancelled_sales=single.cancelled_sales,
                average_order_value=single.average_order_value,
                active_customers_count=active_customers,
                currencies=currencies,
            )

        if len(currencies) == 0:
            # Empty result set
            return TenantSummaryResponse(
                tenant_id=tenant_id,
                date_range=date_filter,
                currency=target_currency,
                total_orders=0,
                gross_sales=Decimal("0.00") if target_currency else None,
                net_sales=Decimal("0.00") if target_currency else None,
                pending_orders_count=0 if target_currency else None,
                pending_sales=Decimal("0.00") if target_currency else None,
                cancelled_orders_count=0 if target_currency else None,
                cancelled_sales=Decimal("0.00") if target_currency else None,
                average_order_value=Decimal("0.00") if target_currency else None,
                active_customers_count=0,
                currencies=[],
            )

        # Multi-currency scenario without a single currency filter:
        # Never sum different currencies into a single total!
        return TenantSummaryResponse(
            tenant_id=tenant_id,
            date_range=date_filter,
            currency=None,
            total_orders=total_orders_all,
            gross_sales=None,
            net_sales=None,
            pending_orders_count=None,
            pending_sales=None,
            cancelled_orders_count=None,
            cancelled_sales=None,
            average_order_value=None,
            active_customers_count=active_customers,
            currencies=currencies,
        )

    def get_tenant_daily_metrics(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> TenantDailyMetricsResponse:
        """
        Retrieves daily aggregated metric time-series from daily_tenant_metrics
        with pagination and filtering.
        """
        self._verify_tenant_exists(tenant_id)
        self._validate_date_range(start_date, end_date)

        target_currency = currency.upper().strip() if currency else None

        base_stmt = select(DailyTenantMetric).where(
            DailyTenantMetric.tenant_id == tenant_id
        )

        if start_date is not None:
            base_stmt = base_stmt.where(DailyTenantMetric.metric_date >= start_date)
        if end_date is not None:
            base_stmt = base_stmt.where(DailyTenantMetric.metric_date <= end_date)
        if target_currency:
            base_stmt = base_stmt.where(DailyTenantMetric.currency == target_currency)

        # Calculate total matching records for pagination
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_records = int(self.session.execute(count_stmt).scalar() or 0)

        total_pages = (
            (total_records + page_size - 1) // page_size if total_records > 0 else 0
        )
        offset = (page - 1) * page_size

        paged_stmt = (
            base_stmt.order_by(
                DailyTenantMetric.metric_date.asc(),
                DailyTenantMetric.currency.asc(),
            )
            .offset(offset)
            .limit(page_size)
        )

        records = self.session.execute(paged_stmt).scalars().all()

        data = [
            DailyMetricRecord(
                metric_date=r.metric_date,
                currency=r.currency,
                orders_count=r.orders_count,
                gross_sales=Decimal(str(r.gross_sales)),
                net_sales=Decimal(str(r.net_sales)),
                pending_orders_count=r.pending_orders_count,
                pending_sales=Decimal(str(r.pending_sales)),
                cancelled_orders_count=r.cancelled_orders_count,
                cancelled_sales=Decimal(str(r.cancelled_sales)),
            )
            for r in records
        ]

        return TenantDailyMetricsResponse(
            tenant_id=tenant_id,
            date_range=DateRangeFilter(start_date=start_date, end_date=end_date),
            currency=target_currency,
            pagination=PaginationMeta(
                total_records=total_records,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            ),
            data=data,
        )

    def get_tenant_product_metrics(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
        product_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> TenantProductMetricsResponse:
        """
        Retrieves precomputed product-level rollups from daily_product_metrics,
        joined with the products catalog table to avoid N+1 queries.
        """
        self._verify_tenant_exists(tenant_id)
        self._validate_date_range(start_date, end_date)

        target_currency = currency.upper().strip() if currency else None

        stmt = (
            select(
                DailyProductMetric.product_id,
                Product.name.label("product_name"),
                Product.sku.label("product_sku"),
                DailyProductMetric.currency,
                func.coalesce(func.sum(DailyProductMetric.units_sold_gross), 0).label("units_sold_gross"),
                func.coalesce(func.sum(DailyProductMetric.units_sold_net), 0).label("units_sold_net"),
                func.coalesce(func.sum(DailyProductMetric.pending_units), 0).label("pending_units"),
                func.coalesce(func.sum(DailyProductMetric.cancelled_units), 0).label("cancelled_units"),
                func.coalesce(func.sum(DailyProductMetric.gross_sales), Decimal("0.00")).label("gross_sales"),
                func.coalesce(func.sum(DailyProductMetric.net_sales), Decimal("0.00")).label("net_sales"),
                func.coalesce(func.sum(DailyProductMetric.pending_sales), Decimal("0.00")).label("pending_sales"),
                func.coalesce(func.sum(DailyProductMetric.cancelled_sales), Decimal("0.00")).label("cancelled_sales"),
                func.coalesce(func.sum(DailyProductMetric.orders_count), 0).label("orders_count"),
            )
            .outerjoin(
                Product,
                and_(
                    Product.id == DailyProductMetric.product_id,
                    Product.tenant_id == DailyProductMetric.tenant_id,
                ),
            )
            .where(DailyProductMetric.tenant_id == tenant_id)
        )

        if start_date is not None:
            stmt = stmt.where(DailyProductMetric.metric_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(DailyProductMetric.metric_date <= end_date)
        if target_currency:
            stmt = stmt.where(DailyProductMetric.currency == target_currency)
        if product_id:
            stmt = stmt.where(DailyProductMetric.product_id == product_id)

        group_stmt = stmt.group_by(
            DailyProductMetric.product_id,
            Product.name,
            Product.sku,
            DailyProductMetric.currency,
        )

        # Count total distinct product-currency entries
        count_stmt = select(func.count()).select_from(group_stmt.subquery())
        total_records = int(self.session.execute(count_stmt).scalar() or 0)

        total_pages = (
            (total_records + page_size - 1) // page_size if total_records > 0 else 0
        )
        offset = (page - 1) * page_size

        # Order by total gross_sales descending, product_id ascending
        paged_stmt = (
            group_stmt.order_by(
                func.sum(DailyProductMetric.gross_sales).desc(),
                DailyProductMetric.product_id.asc(),
            )
            .offset(offset)
            .limit(page_size)
        )

        rows = self.session.execute(paged_stmt).all()

        data = [
            ProductMetricRecord(
                product_id=r.product_id,
                product_name=r.product_name,
                product_sku=r.product_sku,
                currency=r.currency,
                units_sold_gross=int(r.units_sold_gross),
                units_sold_net=int(r.units_sold_net),
                pending_units=int(r.pending_units),
                cancelled_units=int(r.cancelled_units),
                gross_sales=Decimal(str(r.gross_sales)),
                net_sales=Decimal(str(r.net_sales)),
                pending_sales=Decimal(str(r.pending_sales)),
                cancelled_sales=Decimal(str(r.cancelled_sales)),
                orders_count=int(r.orders_count),
            )
            for r in rows
        ]

        return TenantProductMetricsResponse(
            tenant_id=tenant_id,
            date_range=DateRangeFilter(start_date=start_date, end_date=end_date),
            currency=target_currency,
            pagination=PaginationMeta(
                total_records=total_records,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            ),
            data=data,
        )

    def get_manager_summary(
        self,
        manager_user_id: uuid.UUID,
        assigned_tenant_ids: List[uuid.UUID],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
    ) -> ManagerSummaryResponse:
        """
        Retrieves combined performance metrics across all assigned stores for a manager.
        Financial values are strictly separated by currency; different currencies are never combined.
        """
        self._validate_date_range(start_date, end_date)
        target_currency = currency.upper().strip() if currency else None
        date_filter = DateRangeFilter(start_date=start_date, end_date=end_date)

        if not assigned_tenant_ids:
            return ManagerSummaryResponse(
                manager_user_id=manager_user_id,
                assigned_tenants_count=0,
                assigned_tenant_ids=[],
                date_range=date_filter,
                currency=target_currency,
                total_orders=0,
                gross_sales=Decimal("0.00") if target_currency else None,
                net_sales=Decimal("0.00") if target_currency else None,
                pending_orders_count=0 if target_currency else None,
                pending_sales=Decimal("0.00") if target_currency else None,
                cancelled_orders_count=0 if target_currency else None,
                cancelled_sales=Decimal("0.00") if target_currency else None,
                currencies=[],
            )

        stmt = (
            select(
                DailyTenantMetric.currency,
                func.coalesce(func.sum(DailyTenantMetric.orders_count), 0).label("total_orders"),
                func.coalesce(func.sum(DailyTenantMetric.gross_sales), Decimal("0.00")).label("gross_sales"),
                func.coalesce(func.sum(DailyTenantMetric.net_sales), Decimal("0.00")).label("net_sales"),
                func.coalesce(func.sum(DailyTenantMetric.pending_orders_count), 0).label("pending_orders_count"),
                func.coalesce(func.sum(DailyTenantMetric.pending_sales), Decimal("0.00")).label("pending_sales"),
                func.coalesce(func.sum(DailyTenantMetric.cancelled_orders_count), 0).label("cancelled_orders_count"),
                func.coalesce(func.sum(DailyTenantMetric.cancelled_sales), Decimal("0.00")).label("cancelled_sales"),
            )
            .where(DailyTenantMetric.tenant_id.in_(assigned_tenant_ids))
        )

        if start_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date <= end_date)
        if target_currency:
            stmt = stmt.where(DailyTenantMetric.currency == target_currency)

        stmt = stmt.group_by(DailyTenantMetric.currency).order_by(DailyTenantMetric.currency.asc())
        rows = self.session.execute(stmt).all()

        currencies: List[CurrencySummary] = []
        total_orders_all = 0

        for r in rows:
            c_summary = CurrencySummary(
                currency=r.currency,
                total_orders=int(r.total_orders),
                gross_sales=Decimal(str(r.gross_sales)),
                net_sales=Decimal(str(r.net_sales)),
                pending_orders_count=int(r.pending_orders_count),
                pending_sales=Decimal(str(r.pending_sales)),
                cancelled_orders_count=int(r.cancelled_orders_count),
                cancelled_sales=Decimal(str(r.cancelled_sales)),
            )
            currencies.append(c_summary)
            total_orders_all += int(r.total_orders)

        if len(currencies) == 1:
            single = currencies[0]
            return ManagerSummaryResponse(
                manager_user_id=manager_user_id,
                assigned_tenants_count=len(assigned_tenant_ids),
                assigned_tenant_ids=assigned_tenant_ids,
                date_range=date_filter,
                currency=single.currency,
                total_orders=single.total_orders,
                gross_sales=single.gross_sales,
                net_sales=single.net_sales,
                pending_orders_count=single.pending_orders_count,
                pending_sales=single.pending_sales,
                cancelled_orders_count=single.cancelled_orders_count,
                cancelled_sales=single.cancelled_sales,
                currencies=currencies,
            )

        if len(currencies) == 0:
            return ManagerSummaryResponse(
                manager_user_id=manager_user_id,
                assigned_tenants_count=len(assigned_tenant_ids),
                assigned_tenant_ids=assigned_tenant_ids,
                date_range=date_filter,
                currency=target_currency,
                total_orders=0,
                gross_sales=Decimal("0.00") if target_currency else None,
                net_sales=Decimal("0.00") if target_currency else None,
                pending_orders_count=0 if target_currency else None,
                pending_sales=Decimal("0.00") if target_currency else None,
                cancelled_orders_count=0 if target_currency else None,
                cancelled_sales=Decimal("0.00") if target_currency else None,
                currencies=[],
            )

        # Multi-currency scenario without filter: never combine different currencies!
        return ManagerSummaryResponse(
            manager_user_id=manager_user_id,
            assigned_tenants_count=len(assigned_tenant_ids),
            assigned_tenant_ids=assigned_tenant_ids,
            date_range=date_filter,
            currency=None,
            total_orders=total_orders_all,
            gross_sales=None,
            net_sales=None,
            pending_orders_count=None,
            pending_sales=None,
            cancelled_orders_count=None,
            cancelled_sales=None,
            currencies=currencies,
        )

    def get_manager_stores(
        self,
        manager_user_id: uuid.UUID,
        assigned_tenant_ids: List[uuid.UUID],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
    ) -> ManagerStoresResponse:
        """
        Retrieves individual store performance for every assigned tenant store.
        Uses a single grouped query joined with tenants to avoid N+1 queries.
        """
        self._validate_date_range(start_date, end_date)
        target_currency = currency.upper().strip() if currency else None
        date_filter = DateRangeFilter(start_date=start_date, end_date=end_date)

        if not assigned_tenant_ids:
            return ManagerStoresResponse(
                manager_user_id=manager_user_id,
                total_stores=0,
                date_range=date_filter,
                currency=target_currency,
                stores=[],
            )

        tenants = (
            self.session.execute(
                select(Tenant).where(Tenant.id.in_(assigned_tenant_ids))
            )
            .scalars()
            .all()
        )
        tenant_map = {t.id: t for t in tenants}

        stmt = (
            select(
                DailyTenantMetric.tenant_id,
                DailyTenantMetric.currency,
                func.coalesce(func.sum(DailyTenantMetric.orders_count), 0).label("total_orders"),
                func.coalesce(func.sum(DailyTenantMetric.gross_sales), Decimal("0.00")).label("gross_sales"),
                func.coalesce(func.sum(DailyTenantMetric.net_sales), Decimal("0.00")).label("net_sales"),
                func.coalesce(func.sum(DailyTenantMetric.pending_orders_count), 0).label("pending_orders_count"),
                func.coalesce(func.sum(DailyTenantMetric.pending_sales), Decimal("0.00")).label("pending_sales"),
                func.coalesce(func.sum(DailyTenantMetric.cancelled_orders_count), 0).label("cancelled_orders_count"),
                func.coalesce(func.sum(DailyTenantMetric.cancelled_sales), Decimal("0.00")).label("cancelled_sales"),
            )
            .where(DailyTenantMetric.tenant_id.in_(assigned_tenant_ids))
        )

        if start_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date <= end_date)
        if target_currency:
            stmt = stmt.where(DailyTenantMetric.currency == target_currency)

        stmt = stmt.group_by(DailyTenantMetric.tenant_id, DailyTenantMetric.currency)
        rows = self.session.execute(stmt).all()

        store_currencies: dict[uuid.UUID, List[CurrencySummary]] = {
            t_id: [] for t_id in assigned_tenant_ids
        }
        store_orders: dict[uuid.UUID, int] = {t_id: 0 for t_id in assigned_tenant_ids}

        for r in rows:
            c_summary = CurrencySummary(
                currency=r.currency,
                total_orders=int(r.total_orders),
                gross_sales=Decimal(str(r.gross_sales)),
                net_sales=Decimal(str(r.net_sales)),
                pending_orders_count=int(r.pending_orders_count),
                pending_sales=Decimal(str(r.pending_sales)),
                cancelled_orders_count=int(r.cancelled_orders_count),
                cancelled_sales=Decimal(str(r.cancelled_sales)),
            )
            store_currencies[r.tenant_id].append(c_summary)
            store_orders[r.tenant_id] += int(r.total_orders)

        stores: List[StorePerformanceRecord] = []
        for t_id in assigned_tenant_ids:
            t = tenant_map.get(t_id)
            if not t:
                continue
            currs = store_currencies[t_id]
            orders = store_orders[t_id]

            if len(currs) == 1:
                single = currs[0]
                rec = StorePerformanceRecord(
                    tenant_id=t.id,
                    tenant_name=t.name,
                    domain=t.domain,
                    timezone=t.timezone,
                    total_orders=orders,
                    gross_sales=single.gross_sales,
                    net_sales=single.net_sales,
                    pending_orders_count=single.pending_orders_count,
                    pending_sales=single.pending_sales,
                    cancelled_orders_count=single.cancelled_orders_count,
                    cancelled_sales=single.cancelled_sales,
                    currency=single.currency,
                    currencies=currs,
                )
            elif len(currs) == 0:
                rec = StorePerformanceRecord(
                    tenant_id=t.id,
                    tenant_name=t.name,
                    domain=t.domain,
                    timezone=t.timezone,
                    total_orders=0,
                    gross_sales=Decimal("0.00") if target_currency else None,
                    net_sales=Decimal("0.00") if target_currency else None,
                    pending_orders_count=0 if target_currency else None,
                    pending_sales=Decimal("0.00") if target_currency else None,
                    cancelled_orders_count=0 if target_currency else None,
                    cancelled_sales=Decimal("0.00") if target_currency else None,
                    currency=target_currency,
                    currencies=[],
                )
            else:
                rec = StorePerformanceRecord(
                    tenant_id=t.id,
                    tenant_name=t.name,
                    domain=t.domain,
                    timezone=t.timezone,
                    total_orders=orders,
                    gross_sales=None,
                    net_sales=None,
                    pending_orders_count=None,
                    pending_sales=None,
                    cancelled_orders_count=None,
                    cancelled_sales=None,
                    currency=None,
                    currencies=currs,
                )
            stores.append(rec)

        stores.sort(key=lambda s: s.total_orders, reverse=True)

        return ManagerStoresResponse(
            manager_user_id=manager_user_id,
            total_stores=len(stores),
            date_range=date_filter,
            currency=target_currency,
            stores=stores,
        )

    def get_manager_compare(
        self,
        manager_user_id: uuid.UUID,
        target_tenant_ids: List[uuid.UUID],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
    ) -> ManagerCompareResponse:
        """
        Supports direct comparison across assigned stores, ranked by sales and orders.
        """
        stores_resp = self.get_manager_stores(
            manager_user_id=manager_user_id,
            assigned_tenant_ids=target_tenant_ids,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        return ManagerCompareResponse(
            manager_user_id=manager_user_id,
            date_range=stores_resp.date_range,
            currency=stores_resp.currency,
            compared_stores_count=len(stores_resp.stores),
            stores=stores_resp.stores,
        )

    def get_platform_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
    ) -> PlatformSummaryResponse:
        """
        Retrieves platform-wide aggregated metrics across all tenants.
        Only accessible by platform administrators.
        """
        self._validate_date_range(start_date, end_date)
        target_currency = currency.upper().strip() if currency else None
        date_filter = DateRangeFilter(start_date=start_date, end_date=end_date)

        total_tenants = int(self.session.execute(select(func.count(Tenant.id))).scalar() or 0)

        stmt = select(
            DailyTenantMetric.currency,
            func.coalesce(func.sum(DailyTenantMetric.orders_count), 0).label("total_orders"),
            func.coalesce(func.sum(DailyTenantMetric.gross_sales), Decimal("0.00")).label("gross_sales"),
            func.coalesce(func.sum(DailyTenantMetric.net_sales), Decimal("0.00")).label("net_sales"),
            func.coalesce(func.sum(DailyTenantMetric.pending_orders_count), 0).label("pending_orders_count"),
            func.coalesce(func.sum(DailyTenantMetric.pending_sales), Decimal("0.00")).label("pending_sales"),
            func.coalesce(func.sum(DailyTenantMetric.cancelled_orders_count), 0).label("cancelled_orders_count"),
            func.coalesce(func.sum(DailyTenantMetric.cancelled_sales), Decimal("0.00")).label("cancelled_sales"),
        )

        if start_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(DailyTenantMetric.metric_date <= end_date)
        if target_currency:
            stmt = stmt.where(DailyTenantMetric.currency == target_currency)

        stmt = stmt.group_by(DailyTenantMetric.currency).order_by(DailyTenantMetric.currency.asc())
        rows = self.session.execute(stmt).all()

        currencies: List[CurrencySummary] = []
        total_orders_all = 0

        for r in rows:
            c_summary = CurrencySummary(
                currency=r.currency,
                total_orders=int(r.total_orders),
                gross_sales=Decimal(str(r.gross_sales)),
                net_sales=Decimal(str(r.net_sales)),
                pending_orders_count=int(r.pending_orders_count),
                pending_sales=Decimal(str(r.pending_sales)),
                cancelled_orders_count=int(r.cancelled_orders_count),
                cancelled_sales=Decimal(str(r.cancelled_sales)),
            )
            currencies.append(c_summary)
            total_orders_all += int(r.total_orders)

        if len(currencies) == 1:
            single = currencies[0]
            return PlatformSummaryResponse(
                total_tenants=total_tenants,
                date_range=date_filter,
                currency=single.currency,
                total_orders=single.total_orders,
                gross_sales=single.gross_sales,
                net_sales=single.net_sales,
                pending_orders_count=single.pending_orders_count,
                pending_sales=single.pending_sales,
                cancelled_orders_count=single.cancelled_orders_count,
                cancelled_sales=single.cancelled_sales,
                currencies=currencies,
            )

        if len(currencies) == 0:
            return PlatformSummaryResponse(
                total_tenants=total_tenants,
                date_range=date_filter,
                currency=target_currency,
                total_orders=0,
                gross_sales=Decimal("0.00") if target_currency else None,
                net_sales=Decimal("0.00") if target_currency else None,
                pending_orders_count=0 if target_currency else None,
                pending_sales=Decimal("0.00") if target_currency else None,
                cancelled_orders_count=0 if target_currency else None,
                cancelled_sales=Decimal("0.00") if target_currency else None,
                currencies=[],
            )

        return PlatformSummaryResponse(
            total_tenants=total_tenants,
            date_range=date_filter,
            currency=None,
            total_orders=total_orders_all,
            gross_sales=None,
            net_sales=None,
            pending_orders_count=None,
            pending_sales=None,
            cancelled_orders_count=None,
            cancelled_sales=None,
            currencies=currencies,
        )

    def get_active_customers_count(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> int:
        """Count distinct customers who placed orders for this tenant within date range."""
        stmt = select(func.count(func.distinct(Order.customer_id))).where(Order.tenant_id == tenant_id)
        if start_date is not None:
            dt_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            stmt = stmt.where(Order.created_at >= dt_start)
        if end_date is not None:
            dt_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            stmt = stmt.where(Order.created_at <= dt_end)

        return int(self.session.execute(stmt).scalar() or 0)

    def get_order_status_distribution(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
    ) -> OrderStatusDistributionResponse:
        """Computes order status volume and gross revenue breakdown."""
        self._verify_tenant_exists(tenant_id)
        self._validate_date_range(start_date, end_date)

        target_currency = currency.upper().strip() if currency else None

        stmt = (
            select(
                Order.status,
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.total_amount), Decimal("0.00")).label("gross_sales"),
            )
            .where(Order.tenant_id == tenant_id)
        )

        if start_date is not None:
            dt_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            stmt = stmt.where(Order.created_at >= dt_start)
        if end_date is not None:
            dt_end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            stmt = stmt.where(Order.created_at <= dt_end)
        if target_currency:
            stmt = stmt.where(Order.currency == target_currency)

        stmt = stmt.group_by(Order.status)
        rows = self.session.execute(stmt).all()

        status_counts: Dict[str, Tuple[int, Decimal]] = {
            str(r[0]): (int(r[1]), Decimal(str(r[2]))) for r in rows
        }

        # Ensure canonical lifecycle statuses are represented
        all_statuses = ["pending", "paid", "fulfilled", "cancelled"]
        for s in status_counts:
            if s not in all_statuses:
                all_statuses.append(s)

        total_orders = sum(item[0] for item in status_counts.values())

        metrics: List[OrderStatusMetric] = []
        for s in all_statuses:
            count, gross = status_counts.get(s, (0, Decimal("0.00")))
            pct = round((count / total_orders * 100.0), 2) if total_orders > 0 else 0.0
            metrics.append(
                OrderStatusMetric(
                    status=s,
                    orders_count=count,
                    gross_sales=gross,
                    percentage=pct,
                )
            )

        return OrderStatusDistributionResponse(
            tenant_id=tenant_id,
            date_range=DateRangeFilter(start_date=start_date, end_date=end_date),
            currency=target_currency,
            total_orders=total_orders,
            statuses=metrics,
        )

    def get_recent_orders(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> RecentOrdersResponse:
        """Retrieves chronological recent order activity feed with customer metadata."""
        self._verify_tenant_exists(tenant_id)
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20
        page_size = min(page_size, 100)

        total_records = self.session.execute(
            select(func.count(Order.id)).where(Order.tenant_id == tenant_id)
        ).scalar() or 0

        total_pages = (total_records + page_size - 1) // page_size if total_records > 0 else 0
        offset = (page - 1) * page_size

        # Subquery for items count per order to avoid cartesian explosion
        items_subq = (
            select(
                OrderItem.order_id,
                func.count(OrderItem.id).label("items_count"),
            )
            .where(OrderItem.tenant_id == tenant_id)
            .group_by(OrderItem.order_id)
            .subquery()
        )

        stmt = (
            select(
                Order.id,
                Order.external_order_id,
                Order.customer_id,
                Customer.name.label("customer_name"),
                Customer.email.label("customer_email"),
                Order.status,
                Order.currency,
                Order.total_amount,
                func.coalesce(items_subq.c.items_count, 0).label("items_count"),
                Order.created_at,
            )
            .outerjoin(
                Customer,
                and_(
                    Customer.tenant_id == Order.tenant_id,
                    Customer.id == Order.customer_id,
                ),
            )
            .outerjoin(items_subq, items_subq.c.order_id == Order.id)
            .where(Order.tenant_id == tenant_id)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        rows = self.session.execute(stmt).all()

        records = [
            RecentOrderRecord(
                id=r.id,
                external_order_id=r.external_order_id,
                customer_id=r.customer_id,
                customer_name=r.customer_name,
                customer_email=r.customer_email,
                status=r.status,
                currency=r.currency,
                total_amount=Decimal(str(r.total_amount)),
                items_count=int(r.items_count),
                created_at=r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
            )
            for r in rows
        ]

        return RecentOrdersResponse(
            tenant_id=tenant_id,
            pagination=PaginationMeta(
                total_records=total_records,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            ),
            data=records,
        )

    def get_authorized_tenants(self, user: User) -> TenantListResponse:
        """Retrieves list of stores accessible to user based on RBAC role."""
        if user.role == UserRole.PLATFORM_ADMIN.value:
            stmt = select(Tenant).order_by(Tenant.name.asc())
        elif user.role == UserRole.STORE_MANAGER.value:
            stmt = (
                select(Tenant)
                .join(ManagerTenantAssignment, ManagerTenantAssignment.tenant_id == Tenant.id)
                .where(ManagerTenantAssignment.user_id == user.id)
                .order_by(Tenant.name.asc())
            )
        else:  # TENANT_USER
            stmt = select(Tenant).where(Tenant.id == user.tenant_id)

        tenants = self.session.execute(stmt).scalars().all()
        items = [
            TenantListItem(
                id=t.id,
                name=t.name,
                domain=t.domain,
                timezone=t.timezone,
                created_at=t.created_at.isoformat() if hasattr(t.created_at, "isoformat") else str(t.created_at),
            )
            for t in tenants
        ]
        return TenantListResponse(total=len(items), tenants=items)

    def get_tenant_overview(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        currency: Optional[str] = None,
    ) -> TenantOverviewResponse:
        """Composite dashboard overview payload."""
        tenant = self._verify_tenant_exists(tenant_id)
        summary = self.get_tenant_summary(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        status_dist = self.get_order_status_distribution(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        recent_orders = self.get_recent_orders(tenant_id=tenant_id, page=1, page_size=10)
        top_products = self.get_tenant_product_metrics(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            page=1,
            page_size=5,
        )

        return TenantOverviewResponse(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_domain=tenant.domain,
            summary=summary,
            status_distribution=status_dist.statuses,
            recent_orders=recent_orders.data,
            top_products=top_products.data,
        )
