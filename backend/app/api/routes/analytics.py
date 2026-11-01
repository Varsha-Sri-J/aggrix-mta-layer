"""
AGGRIX Analytics Read API Routes (Protected by RBAC).

Exposes precomputed multi-tenant analytical metrics:
- GET /api/v1/analytics/tenants/{tenant_id}/summary
- GET /api/v1/analytics/tenants/{tenant_id}/daily
- GET /api/v1/analytics/tenants/{tenant_id}/products

Security & Authorization Enforcement:
------------------------------------
All endpoints require a valid JWT Bearer token.
Access to {tenant_id} is strictly checked via `get_authorized_tenant`:
- Tenant Users: Can only access their own tenant store.
- Store Managers: Can only access explicitly assigned stores.
- Platform Admins: Can access any store.
Unauthorized attempts return 401 (unauthenticated) or 403 (forbidden).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timezone
from typing import Optional, Set

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.broadcaster import broadcaster
from app.analytics.service import (
    AnalyticsQueryService,
    InvalidDateRangeError,
    TenantNotFoundError,
)
from app.api.deps import get_authorized_tenant, get_current_user
from app.database.connection import get_db
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.analytics import (
    OrderStatusDistributionResponse,
    RecentOrdersResponse,
    TenantDailyMetricsResponse,
    TenantListItem,
    TenantListResponse,
    TenantOverviewResponse,
    TenantProductMetricsResponse,
    TenantSummaryResponse,
)

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/summary",
    response_model=TenantSummaryResponse,
    summary="Get Tenant Analytics Summary",
    description=(
        "Retrieves precomputed aggregate metrics for a tenant, including total orders, "
        "gross and net sales, pending and cancelled volume, and segregated currency breakdown. "
        "Requires authentication and tenant authorization. "
        "Financial totals are never combined across different currencies."
    ),
    responses={
        200: {"description": "Analytics summary retrieved successfully."},
        400: {"description": "Invalid query parameters (e.g., start_date > end_date)."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden: caller not authorized for this tenant."},
        404: {"description": "Target tenant not found."},
    },
)
def get_tenant_summary(
    tenant_id: uuid.UUID = Path(..., description="Target tenant UUID"),
    start_date: Optional[date] = Query(
        None, description="Inclusive start date filter (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None, description="Inclusive end date filter (YYYY-MM-DD)"
    ),
    currency: Optional[str] = Query(
        None,
        min_length=3,
        max_length=3,
        description="Filter summary by ISO 4217 3-letter currency code (e.g. USD, EUR, INR)",
    ),
    authorized_tenant: Tenant = Depends(get_authorized_tenant),
    db: Session = Depends(get_db),
) -> TenantSummaryResponse:
    """Read API retrieving tenant-level performance summary rollups."""
    service = AnalyticsQueryService(db)
    try:
        return service.get_tenant_summary(
            tenant_id=authorized_tenant.id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/tenants/{tenant_id}/daily",
    response_model=TenantDailyMetricsResponse,
    summary="Get Tenant Daily Aggregated Metrics",
    description=(
        "Retrieves chronological daily aggregated metric records for an authorized tenant within "
        "an optional date window and currency filter, supporting pagination."
    ),
    responses={
        200: {"description": "Daily metrics retrieved successfully."},
        400: {"description": "Invalid query parameters (e.g., start_date > end_date)."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden: caller not authorized for this tenant."},
        404: {"description": "Target tenant not found."},
    },
)
def get_tenant_daily_metrics(
    tenant_id: uuid.UUID = Path(..., description="Target tenant UUID"),
    start_date: Optional[date] = Query(
        None, description="Inclusive start date filter (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None, description="Inclusive end date filter (YYYY-MM-DD)"
    ),
    currency: Optional[str] = Query(
        None,
        min_length=3,
        max_length=3,
        description="Filter daily metrics by ISO 4217 3-letter currency code",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=250, description="Records per page (max 250)"),
    authorized_tenant: Tenant = Depends(get_authorized_tenant),
    db: Session = Depends(get_db),
) -> TenantDailyMetricsResponse:
    """Read API retrieving paginated daily tenant metrics."""
    service = AnalyticsQueryService(db)
    try:
        return service.get_tenant_daily_metrics(
            tenant_id=authorized_tenant.id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            page=page,
            page_size=page_size,
        )
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/tenants/{tenant_id}/products",
    response_model=TenantProductMetricsResponse,
    summary="Get Tenant Product-Level Analytics",
    description=(
        "Retrieves precomputed product-level rollups including gross/net units sold, "
        "pending/cancelled units, revenue, and orders count, joined with product catalog metadata. "
        "Results are ordered by gross sales descending."
    ),
    responses={
        200: {"description": "Product metrics retrieved successfully."},
        400: {"description": "Invalid query parameters (e.g., start_date > end_date)."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden: caller not authorized for this tenant."},
        404: {"description": "Target tenant not found."},
    },
)
def get_tenant_product_metrics(
    tenant_id: uuid.UUID = Path(..., description="Target tenant UUID"),
    start_date: Optional[date] = Query(
        None, description="Inclusive start date filter (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None, description="Inclusive end date filter (YYYY-MM-DD)"
    ),
    currency: Optional[str] = Query(
        None,
        min_length=3,
        max_length=3,
        description="Filter product metrics by ISO 4217 3-letter currency code",
    ),
    product_id: Optional[uuid.UUID] = Query(
        None, description="Filter metrics by specific product UUID"
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=250, description="Records per page (max 250)"),
    authorized_tenant: Tenant = Depends(get_authorized_tenant),
    db: Session = Depends(get_db),
) -> TenantProductMetricsResponse:
    """Read API retrieving paginated product-level aggregated metrics."""
    service = AnalyticsQueryService(db)
    try:
        return service.get_tenant_product_metrics(
            tenant_id=authorized_tenant.id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            product_id=product_id,
            page=page,
            page_size=page_size,
        )
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/stream",
    summary="Real-Time Analytics Event Stream (SSE)",
    description=(
        "Establishes a persistent Server-Sent Events (SSE) stream for live analytics updates. "
        "Authenticated via Authorization header or ?token= query parameter. "
        "Strictly enforces tenant isolation: tenants only receive their own store events. "
        "Supports client reconnection via Last-Event-ID header and periodic heartbeats."
    ),
    responses={
        200: {"description": "Persistent SSE connection established."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden for requested tenant scope."},
    },
)
async def stream_analytics_events(
    tenant_id: Optional[uuid.UUID] = Query(None, description="Optional tenant UUID to filter event stream"),
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID", description="Reconnection event ID"),
    last_event_id_query: Optional[str] = Query(None, alias="last_event_id", description="Reconnection event ID query param"),
    max_events: Optional[int] = Query(None, ge=1, description="Optional maximum events count before closing stream (for testing and probes)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Server-Sent Events endpoint streaming live analytics updates with tenancy isolation."""
    effective_last_id = last_event_id or last_event_id_query

    # Determine authorized tenant scope
    authorized_tenant_ids: Optional[Set[uuid.UUID]] = None

    if current_user.role == UserRole.PLATFORM_ADMIN.value:
        authorized_tenant_ids = None  # All stores permitted
    elif current_user.role == UserRole.STORE_MANAGER.value:
        assignments = db.execute(
            select(ManagerTenantAssignment.tenant_id).where(
                ManagerTenantAssignment.user_id == current_user.id
            )
        ).scalars().all()
        authorized_tenant_ids = set(assignments)
    elif current_user.role == UserRole.TENANT_USER.value:
        authorized_tenant_ids = {current_user.tenant_id}
        if tenant_id is None:
            tenant_id = current_user.tenant_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unrecognized user role.",
        )

    # Validate requested filter_tenant_id if provided
    if tenant_id is not None:
        if authorized_tenant_ids is not None and tenant_id not in authorized_tenant_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: caller is not authorized to stream events for tenant {tenant_id}.",
            )

    sub = broadcaster.subscribe(
        user_id=current_user.id,
        role=current_user.role,
        authorized_tenant_ids=authorized_tenant_ids,
        filter_tenant_id=tenant_id,
    )

    async def event_generator():
        delivered = 0
        try:
            # 1. Connection acknowledgment
            init_data = json.dumps({
                "status": "connected",
                "client_id": sub.client_id,
                "user_id": str(current_user.id),
                "role": current_user.role,
                "filter_tenant_id": str(tenant_id) if tenant_id else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            yield f"id: init\nevent: connected\ndata: {init_data}\n\n"
            delivered += 1
            if max_events is not None and delivered >= max_events:
                return

            # 2. Replay buffered events since last_event_id if requested
            if effective_last_id:
                replayed = broadcaster.get_events_since(effective_last_id, sub)
                for ev in replayed:
                    yield ev.to_sse_message()
                    delivered += 1
                    if max_events is not None and delivered >= max_events:
                        return

            # 3. Stream live events with heartbeats
            while True:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    if event is not None:
                        yield event.to_sse_message()
                        delivered += 1
                        if max_events is not None and delivered >= max_events:
                            return
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe(sub.client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/tenants",
    response_model=TenantListResponse,
    summary="List Accessible Tenant Stores",
    description="Returns all tenant stores accessible to the authenticated user based on role.",
    responses={
        200: {"description": "List of accessible tenant stores retrieved successfully."},
        401: {"description": "Missing or invalid authentication token."},
    },
)
def get_accessible_tenants(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantListResponse:
    """Read API retrieving list of stores authorized for current user."""
    service = AnalyticsQueryService(db)
    return service.get_authorized_tenants(current_user)


@router.get(
    "/tenants/{tenant_id}/status-distribution",
    response_model=OrderStatusDistributionResponse,
    summary="Get Order Status Distribution",
    description="Returns order volume and revenue grouped by order status with percentage breakdowns.",
    responses={
        200: {"description": "Order status distribution retrieved successfully."},
        400: {"description": "Invalid date range parameters."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden for this tenant."},
        404: {"description": "Target tenant not found."},
    },
)
def get_order_status_distribution(
    tenant_id: uuid.UUID = Path(..., description="Target tenant UUID"),
    start_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    currency: Optional[str] = Query(None, min_length=3, max_length=3, description="Currency filter"),
    authorized_tenant: Tenant = Depends(get_authorized_tenant),
    db: Session = Depends(get_db),
) -> OrderStatusDistributionResponse:
    """Read API retrieving order status distribution."""
    service = AnalyticsQueryService(db)
    try:
        return service.get_order_status_distribution(
            tenant_id=authorized_tenant.id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except InvalidDateRangeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/tenants/{tenant_id}/recent-orders",
    response_model=RecentOrdersResponse,
    summary="Get Recent Orders Activity",
    description="Returns a chronological feed of recent order activity with customer and item count metadata.",
    responses={
        200: {"description": "Recent orders feed retrieved successfully."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden for this tenant."},
        404: {"description": "Target tenant not found."},
    },
)
def get_recent_orders(
    tenant_id: uuid.UUID = Path(..., description="Target tenant UUID"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page (max 100)"),
    authorized_tenant: Tenant = Depends(get_authorized_tenant),
    db: Session = Depends(get_db),
) -> RecentOrdersResponse:
    """Read API retrieving chronological recent orders activity feed."""
    service = AnalyticsQueryService(db)
    return service.get_recent_orders(
        tenant_id=authorized_tenant.id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/tenants/{tenant_id}/overview",
    response_model=TenantOverviewResponse,
    summary="Get Composite Tenant Dashboard Overview",
    description="Returns composite dashboard data including KPI summary, status distribution, recent activity, and top products.",
    responses={
        200: {"description": "Overview metrics retrieved successfully."},
        400: {"description": "Invalid date range parameters."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden for this tenant."},
        404: {"description": "Target tenant not found."},
    },
)
def get_tenant_overview(
    tenant_id: uuid.UUID = Path(..., description="Target tenant UUID"),
    start_date: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD)"),
    currency: Optional[str] = Query(None, min_length=3, max_length=3, description="Currency filter"),
    authorized_tenant: Tenant = Depends(get_authorized_tenant),
    db: Session = Depends(get_db),
) -> TenantOverviewResponse:
    """Read API retrieving composite tenant overview for dashboard initialization."""
    service = AnalyticsQueryService(db)
    try:
        return service.get_tenant_overview(
            tenant_id=authorized_tenant.id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except InvalidDateRangeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
