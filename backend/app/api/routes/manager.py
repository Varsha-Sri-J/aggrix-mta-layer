"""
AGGRIX Multi-Store Manager Analytics Routes.

Exposes authorized cross-tenant metrics across explicitly assigned stores:
- GET /api/v1/analytics/manager/summary
- GET /api/v1/analytics/manager/stores
- GET /api/v1/analytics/manager/compare

Security & RBAC Enforcement:
- Restricted strictly to Multi-Store Managers and Platform Administrators.
- Store managers can query only explicitly assigned stores.
- Tenant users are rejected with 403 Forbidden.
- Cross-tenant data leakage is strictly prevented.
- Financial metrics preserve strict currency separation (never combine different currencies).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analytics.service import AnalyticsQueryService, InvalidDateRangeError
from app.api.deps import get_current_user, get_manager_assigned_tenant_ids
from app.database.connection import get_db
from app.models.user import User, UserRole
from app.schemas.manager import (
    ManagerCompareResponse,
    ManagerStoresResponse,
    ManagerSummaryResponse,
)

router = APIRouter()


@router.get(
    "/summary",
    response_model=ManagerSummaryResponse,
    summary="Get Multi-Store Manager Combined Summary",
    description=(
        "Retrieves aggregate performance metrics across all explicitly assigned stores for a manager. "
        "Strictly segregates currencies; different currencies are never combined into a single total."
    ),
    responses={
        200: {"description": "Manager summary retrieved successfully."},
        400: {"description": "Invalid query parameters (e.g. start_date > end_date)."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden: store manager or platform admin role required."},
    },
)
def get_manager_summary(
    start_date: Optional[date] = Query(None, description="Start date (inclusive, YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive, YYYY-MM-DD)"),
    currency: Optional[str] = Query(None, min_length=3, max_length=3, description="ISO currency code"),
    tenant_ids: Optional[List[uuid.UUID]] = Query(
        None, description="Optional subset of assigned tenant IDs to aggregate"
    ),
    current_user: User = Depends(get_current_user),
    assigned_tenants: List[uuid.UUID] = Depends(get_manager_assigned_tenant_ids),
    db: Session = Depends(get_db),
) -> ManagerSummaryResponse:
    """Combines metrics across authenticated manager's assigned stores."""
    # If client passed tenant_ids filter, ensure they are a subset of assigned stores
    effective_tenant_ids = assigned_tenants
    if tenant_ids is not None:
        assigned_set = set(assigned_tenants)
        for t_id in tenant_ids:
            if t_id not in assigned_set and current_user.role != UserRole.PLATFORM_ADMIN.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: manager is not assigned to store '{t_id}'.",
                )
        effective_tenant_ids = [t for t in tenant_ids if t in assigned_set or current_user.role == UserRole.PLATFORM_ADMIN.value]

    service = AnalyticsQueryService(db)
    try:
        return service.get_manager_summary(
            manager_user_id=current_user.id,
            assigned_tenant_ids=effective_tenant_ids,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/stores",
    response_model=ManagerStoresResponse,
    summary="Get Assigned Stores Performance Breakdown",
    description=(
        "Returns individual metric rollups for each store explicitly assigned to the manager. "
        "Avoids N+1 queries by joining tenant metadata in a single grouped aggregation."
    ),
    responses={
        200: {"description": "Stores breakdown retrieved successfully."},
        400: {"description": "Invalid query parameters."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden: store manager or platform admin role required."},
    },
)
def get_manager_stores(
    start_date: Optional[date] = Query(None, description="Start date (inclusive, YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive, YYYY-MM-DD)"),
    currency: Optional[str] = Query(None, min_length=3, max_length=3, description="ISO currency code"),
    current_user: User = Depends(get_current_user),
    assigned_tenants: List[uuid.UUID] = Depends(get_manager_assigned_tenant_ids),
    db: Session = Depends(get_db),
) -> ManagerStoresResponse:
    """Returns individual performance for every assigned store."""
    service = AnalyticsQueryService(db)
    try:
        return service.get_manager_stores(
            manager_user_id=current_user.id,
            assigned_tenant_ids=assigned_tenants,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/compare",
    response_model=ManagerCompareResponse,
    summary="Compare Assigned Stores Performance",
    description=(
        "Supports direct comparative evaluation across assigned stores. "
        "Enforces that only authorized assigned stores can be compared."
    ),
    responses={
        200: {"description": "Store comparison retrieved successfully."},
        400: {"description": "Invalid query parameters."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden: store manager or platform admin role required."},
    },
)
def get_manager_compare(
    tenant_ids: Optional[List[uuid.UUID]] = Query(
        None, description="Specific assigned store IDs to compare (defaults to all assigned)"
    ),
    start_date: Optional[date] = Query(None, description="Start date (inclusive, YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive, YYYY-MM-DD)"),
    currency: Optional[str] = Query(None, min_length=3, max_length=3, description="ISO currency code"),
    current_user: User = Depends(get_current_user),
    assigned_tenants: List[uuid.UUID] = Depends(get_manager_assigned_tenant_ids),
    db: Session = Depends(get_db),
) -> ManagerCompareResponse:
    """Compares assigned stores performance."""
    effective_tenant_ids = assigned_tenants
    if tenant_ids is not None:
        assigned_set = set(assigned_tenants)
        for t_id in tenant_ids:
            if t_id not in assigned_set and current_user.role != UserRole.PLATFORM_ADMIN.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: manager is not assigned to store '{t_id}'.",
                )
        effective_tenant_ids = [t for t in tenant_ids if t in assigned_set or current_user.role == UserRole.PLATFORM_ADMIN.value]

    service = AnalyticsQueryService(db)
    try:
        return service.get_manager_compare(
            manager_user_id=current_user.id,
            target_tenant_ids=effective_tenant_ids,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
