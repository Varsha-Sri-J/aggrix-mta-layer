"""
AGGRIX Platform Administrator Analytics Routes.

Exposes platform-wide aggregated metrics across all system tenants:
- GET /api/v1/analytics/platform/summary

Security & RBAC Enforcement:
- Restricted strictly to Platform Administrators (`require_platform_admin`).
- Requests from tenant users or store managers are rejected with 403 Forbidden.
- Preserves exact currency separation across all platform stores.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analytics.service import AnalyticsQueryService, InvalidDateRangeError
from app.api.deps import require_platform_admin
from app.database.connection import get_db
from app.models.user import User
from app.schemas.manager import PlatformSummaryResponse

router = APIRouter()


@router.get(
    "/summary",
    response_model=PlatformSummaryResponse,
    summary="Get Platform-Wide Analytics Summary",
    description=(
        "Retrieves platform-wide order counts and currency-separated financial summaries "
        "across all tenants in the system. Accessible exclusively by Platform Administrators."
    ),
    responses={
        200: {"description": "Platform summary retrieved successfully."},
        400: {"description": "Invalid query parameters."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Access forbidden: platform administrator role required."},
    },
)
def get_platform_summary(
    start_date: Optional[date] = Query(None, description="Start date (inclusive, YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive, YYYY-MM-DD)"),
    currency: Optional[str] = Query(None, min_length=3, max_length=3, description="ISO currency code"),
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> PlatformSummaryResponse:
    """Returns platform-wide metrics across all stores. Platform Admin only."""
    service = AnalyticsQueryService(db)
    try:
        return service.get_platform_summary(
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
