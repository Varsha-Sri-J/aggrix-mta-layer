"""Pydantic v2 schemas for AGGRIX Analytics Read APIs."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DateRangeFilter(BaseModel):
    """Filter bounds representing the requested or effective metric window."""

    model_config = ConfigDict(from_attributes=True)

    start_date: Optional[date] = Field(
        None,
        description="Inclusive start date (YYYY-MM-DD). If omitted, unbounded from historical start.",
    )
    end_date: Optional[date] = Field(
        None,
        description="Inclusive end date (YYYY-MM-DD). If omitted, unbounded up to latest data.",
    )


class CurrencySummary(BaseModel):
    """Aggregated financial and volume metrics for a specific currency."""

    model_config = ConfigDict(from_attributes=True)

    currency: str = Field(..., description="ISO 4217 3-letter currency code (e.g. USD, EUR, GBP)")
    total_orders: int = Field(..., ge=0, description="Total order volume across all lifecycle statuses")
    gross_sales: Decimal = Field(..., ge=0, description="Total gross revenue placed in this currency")
    net_sales: Decimal = Field(..., ge=0, description="Recognized net sales (paid + fulfilled orders)")
    pending_orders_count: int = Field(..., ge=0, description="Orders currently awaiting payment capture")
    pending_sales: Decimal = Field(..., ge=0, description="Total revenue tied up in pending orders")
    cancelled_orders_count: int = Field(..., ge=0, description="Cancelled orders count")
    cancelled_sales: Decimal = Field(..., ge=0, description="Total cancelled/refunded revenue")
    average_order_value: Optional[Decimal] = Field(
        None, ge=0, description="Average order value (gross_sales / total_orders)"
    )


class TenantSummaryResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/tenants/{tenant_id}/summary.

    Note on Currency Isolation:
    Financial totals (gross_sales, net_sales, etc.) are only populated at the root level
    when a single currency is requested or present. Multi-currency aggregation is strictly
    segregated in the 'currencies' list to prevent cross-currency summation.
    """

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID = Field(..., description="Target tenant identifier")
    date_range: DateRangeFilter = Field(..., description="Applied date range filter")
    currency: Optional[str] = Field(
        None,
        description="Filtered currency code if single-currency filter was applied",
    )
    total_orders: int = Field(..., ge=0, description="Total order count across all currencies")
    gross_sales: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Total gross sales if single currency; None for multi-currency",
    )
    net_sales: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Total net sales if single currency; None for multi-currency",
    )
    pending_orders_count: Optional[int] = Field(
        None,
        ge=0,
        description="Pending orders if single currency; None for multi-currency",
    )
    pending_sales: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Total pending sales if single currency; None for multi-currency",
    )
    cancelled_orders_count: Optional[int] = Field(
        None,
        ge=0,
        description="Cancelled orders if single currency; None for multi-currency",
    )
    cancelled_sales: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Total cancelled sales if single currency; None for multi-currency",
    )
    average_order_value: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Average order value for single currency (gross_sales / total_orders)",
    )
    active_customers_count: Optional[int] = Field(
        None,
        ge=0,
        description="Count of distinct customers who placed orders within the date window",
    )
    currencies: List[CurrencySummary] = Field(
        default_factory=list,
        description="Segregated currency-level summaries preserving exact accounting",
    )


class PaginationMeta(BaseModel):
    """Standardized pagination metadata."""

    model_config = ConfigDict(from_attributes=True)

    total_records: int = Field(..., ge=0, description="Total matching records across all pages")
    page: int = Field(..., ge=1, description="Current 1-indexed page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total calculated pages")


class DailyMetricRecord(BaseModel):
    """Daily aggregated metric record for a tenant."""

    model_config = ConfigDict(from_attributes=True)

    metric_date: date = Field(..., description="Date of the metric bucket in tenant local time")
    currency: str = Field(..., description="ISO 4217 3-letter currency code")
    orders_count: int = Field(..., ge=0, description="Orders placed on this date")
    gross_sales: Decimal = Field(..., ge=0, description="Gross sales placed on this date")
    net_sales: Decimal = Field(..., ge=0, description="Recognized net sales placed on this date")
    pending_orders_count: int = Field(..., ge=0, description="Pending orders count")
    pending_sales: Decimal = Field(..., ge=0, description="Pending revenue")
    cancelled_orders_count: int = Field(..., ge=0, description="Cancelled orders count")
    cancelled_sales: Decimal = Field(..., ge=0, description="Cancelled revenue")


class TenantDailyMetricsResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/tenants/{tenant_id}/daily."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID = Field(..., description="Target tenant identifier")
    date_range: DateRangeFilter = Field(..., description="Applied date range filter")
    currency: Optional[str] = Field(None, description="Applied currency filter")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
    data: List[DailyMetricRecord] = Field(..., description="Ordered list of daily metrics")


class ProductMetricRecord(BaseModel):
    """Aggregated analytics metrics for an individual product."""

    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID = Field(..., description="Product UUID")
    product_name: Optional[str] = Field(None, description="Product catalog name")
    product_sku: Optional[str] = Field(None, description="Product SKU code")
    currency: str = Field(..., description="ISO 4217 3-letter currency code")
    units_sold_gross: int = Field(..., ge=0, description="Total gross units ordered")
    units_sold_net: int = Field(..., ge=0, description="Recognized net units sold")
    pending_units: int = Field(..., ge=0, description="Units in pending orders")
    cancelled_units: int = Field(..., ge=0, description="Units in cancelled/refunded orders")
    gross_sales: Decimal = Field(..., ge=0, description="Gross product revenue")
    net_sales: Decimal = Field(..., ge=0, description="Recognized net product revenue")
    pending_sales: Decimal = Field(..., ge=0, description="Pending product revenue")
    cancelled_sales: Decimal = Field(..., ge=0, description="Cancelled product revenue")
    orders_count: int = Field(..., ge=0, description="Count of distinct orders containing this product")


class TenantProductMetricsResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/tenants/{tenant_id}/products."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID = Field(..., description="Target tenant identifier")
    date_range: DateRangeFilter = Field(..., description="Applied date range filter")
    currency: Optional[str] = Field(None, description="Applied currency filter")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
    data: List[ProductMetricRecord] = Field(..., description="Ordered list of product metrics")


class OrderStatusMetric(BaseModel):
    """Metrics breakdown for a single order lifecycle status."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Order lifecycle status (pending, paid, fulfilled, cancelled)")
    orders_count: int = Field(..., ge=0, description="Count of orders in this status")
    gross_sales: Decimal = Field(..., ge=0, description="Total gross revenue associated with this status")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total order count")


class OrderStatusDistributionResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/tenants/{tenant_id}/status-distribution."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID = Field(..., description="Target tenant identifier")
    date_range: DateRangeFilter = Field(..., description="Applied date range filter")
    currency: Optional[str] = Field(None, description="Applied currency filter")
    total_orders: int = Field(..., ge=0, description="Total order volume")
    statuses: List[OrderStatusMetric] = Field(..., description="Breakdown per status")


class RecentOrderRecord(BaseModel):
    """Individual record representing recent order activity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Order primary key UUID")
    external_order_id: str = Field(..., description="External order reference (e.g. SHP-001234)")
    customer_id: uuid.UUID = Field(..., description="Customer UUID")
    customer_name: Optional[str] = Field(None, description="Customer full name")
    customer_email: Optional[str] = Field(None, description="Customer email address")
    status: str = Field(..., description="Order lifecycle status")
    currency: str = Field(..., description="ISO 4217 3-letter currency code")
    total_amount: Decimal = Field(..., ge=0, description="Order total monetary amount")
    items_count: int = Field(..., ge=0, description="Count of line items in order")
    created_at: str = Field(..., description="ISO 8601 placement timestamp in UTC")


class RecentOrdersResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/tenants/{tenant_id}/recent-orders."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID = Field(..., description="Target tenant identifier")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
    data: List[RecentOrderRecord] = Field(..., description="Chronological recent order feed")


class TenantListItem(BaseModel):
    """Tenant store descriptor for tenant switcher dropdowns."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Tenant UUID")
    name: str = Field(..., description="Store business name")
    domain: str = Field(..., description="Store subdomain/domain")
    timezone: str = Field(..., description="Operational timezone")
    created_at: str = Field(..., description="Onboarding timestamp")


class TenantListResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/tenants."""

    model_config = ConfigDict(from_attributes=True)

    total: int = Field(..., ge=0, description="Total authorized stores available to user")
    tenants: List[TenantListItem] = Field(..., description="List of authorized store descriptors")


class TenantOverviewResponse(BaseModel):
    """Composite dashboard overview payload combining summary KPIs, trends, and top products."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID = Field(..., description="Target tenant UUID")
    tenant_name: str = Field(..., description="Store business name")
    tenant_domain: str = Field(..., description="Store domain")
    summary: TenantSummaryResponse = Field(..., description="Core revenue and orders summary")
    status_distribution: List[OrderStatusMetric] = Field(..., description="Order status breakdown")
    recent_orders: List[RecentOrderRecord] = Field(..., description="Latest activity feed")
    top_products: List[ProductMetricRecord] = Field(..., description="Top 5 revenue products")

