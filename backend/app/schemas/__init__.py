"""Schemas package for AGGRIX API request and response models."""

from app.schemas.analytics import (
    CurrencySummary,
    DailyMetricRecord,
    DateRangeFilter,
    PaginationMeta,
    ProductMetricRecord,
    TenantDailyMetricsResponse,
    TenantProductMetricsResponse,
    TenantSummaryResponse,
)
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UserCreateRequest,
    UserProvisionRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.manager import (
    ManagerCompareResponse,
    ManagerStoresResponse,
    ManagerSummaryResponse,
    PlatformSummaryResponse,
    StorePerformanceRecord,
)

__all__ = [
    "DateRangeFilter",
    "CurrencySummary",
    "TenantSummaryResponse",
    "PaginationMeta",
    "DailyMetricRecord",
    "TenantDailyMetricsResponse",
    "ProductMetricRecord",
    "TenantProductMetricsResponse",
    "LoginRequest",
    "TokenResponse",
    "UserResponse",
    "UserCreateRequest",
    "UserRegisterRequest",
    "UserProvisionRequest",
    "ManagerSummaryResponse",
    "StorePerformanceRecord",
    "ManagerStoresResponse",
    "ManagerCompareResponse",
    "PlatformSummaryResponse",
]
