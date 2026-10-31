"""Pydantic v2 schemas for Manager and Platform Analytics."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analytics import CurrencySummary, DateRangeFilter


class ManagerSummaryResponse(BaseModel):
    """
    Combined aggregate performance metrics across all explicitly assigned stores for a manager.
    Currency segregation rule: Financial values are never combined across different currencies.
    """

    model_config = ConfigDict(from_attributes=True)

    manager_user_id: uuid.UUID = Field(..., description="Authenticated manager UUID")
    assigned_tenants_count: int = Field(..., ge=0, description="Number of assigned tenants evaluated")
    assigned_tenant_ids: List[uuid.UUID] = Field(..., description="List of evaluated tenant UUIDs")
    date_range: DateRangeFilter = Field(..., description="Applied date range window")
    currency: Optional[str] = Field(None, description="Single currency filter if applied")
    total_orders: int = Field(..., ge=0, description="Combined order count across assigned stores")
    gross_sales: Optional[Decimal] = Field(None, ge=0, description="Gross revenue (single currency)")
    net_sales: Optional[Decimal] = Field(None, ge=0, description="Net revenue (single currency)")
    pending_orders_count: Optional[int] = Field(None, ge=0, description="Pending orders count")
    pending_sales: Optional[Decimal] = Field(None, ge=0, description="Pending revenue (single currency)")
    cancelled_orders_count: Optional[int] = Field(None, ge=0, description="Cancelled orders count")
    cancelled_sales: Optional[Decimal] = Field(None, ge=0, description="Cancelled revenue (single currency)")
    currencies: List[CurrencySummary] = Field(
        default_factory=list,
        description="Segregated metrics per currency across assigned stores",
    )


class StorePerformanceRecord(BaseModel):
    """Performance metrics rollup for an individual assigned tenant store."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID = Field(..., description="Tenant identifier")
    tenant_name: str = Field(..., description="Store display name")
    domain: str = Field(..., description="Store domain")
    timezone: str = Field(..., description="Store operational timezone")
    total_orders: int = Field(..., ge=0, description="Total order volume")
    gross_sales: Optional[Decimal] = Field(None, ge=0, description="Gross sales (single currency)")
    net_sales: Optional[Decimal] = Field(None, ge=0, description="Net sales (single currency)")
    pending_orders_count: Optional[int] = Field(None, ge=0, description="Pending orders count")
    pending_sales: Optional[Decimal] = Field(None, ge=0, description="Pending sales (single currency)")
    cancelled_orders_count: Optional[int] = Field(None, ge=0, description="Cancelled orders count")
    cancelled_sales: Optional[Decimal] = Field(None, ge=0, description="Cancelled sales (single currency)")
    currency: Optional[str] = Field(None, description="Primary currency if single")
    currencies: List[CurrencySummary] = Field(
        default_factory=list,
        description="Currency breakdown for this store",
    )


class ManagerStoresResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/manager/stores."""

    model_config = ConfigDict(from_attributes=True)

    manager_user_id: uuid.UUID = Field(..., description="Authenticated manager UUID")
    total_stores: int = Field(..., ge=0, description="Total assigned stores count")
    date_range: DateRangeFilter = Field(..., description="Applied date range window")
    currency: Optional[str] = Field(None, description="Single currency filter if applied")
    stores: List[StorePerformanceRecord] = Field(
        default_factory=list,
        description="Performance rollups for each assigned store",
    )


class ManagerCompareResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/manager/compare."""

    model_config = ConfigDict(from_attributes=True)

    manager_user_id: uuid.UUID = Field(..., description="Authenticated manager UUID")
    date_range: DateRangeFilter = Field(..., description="Applied date range window")
    currency: Optional[str] = Field(None, description="Single currency filter if applied")
    compared_stores_count: int = Field(..., ge=0, description="Number of stores compared")
    stores: List[StorePerformanceRecord] = Field(
        default_factory=list,
        description="Store performance records sorted for comparative evaluation",
    )


class PlatformSummaryResponse(BaseModel):
    """Response payload for GET /api/v1/analytics/platform/summary."""

    model_config = ConfigDict(from_attributes=True)

    total_tenants: int = Field(..., ge=0, description="Total active tenants in the platform")
    date_range: DateRangeFilter = Field(..., description="Applied date range window")
    currency: Optional[str] = Field(None, description="Single currency filter if applied")
    total_orders: int = Field(..., ge=0, description="Combined orders across all platform tenants")
    gross_sales: Optional[Decimal] = Field(None, ge=0, description="Platform gross revenue (single currency)")
    net_sales: Optional[Decimal] = Field(None, ge=0, description="Platform net revenue (single currency)")
    pending_orders_count: Optional[int] = Field(None, ge=0, description="Pending orders count")
    pending_sales: Optional[Decimal] = Field(None, ge=0, description="Pending revenue (single currency)")
    cancelled_orders_count: Optional[int] = Field(None, ge=0, description="Cancelled orders count")
    cancelled_sales: Optional[Decimal] = Field(None, ge=0, description="Cancelled revenue (single currency)")
    currencies: List[CurrencySummary] = Field(
        default_factory=list,
        description="Platform-wide segregated metrics per currency",
    )
