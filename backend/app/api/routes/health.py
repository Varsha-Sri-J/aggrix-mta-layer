"""
Health Check API Routes
AGGRIX MTA Layer
"""

from typing import Optional
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.connection import check_db_connection, get_db

router = APIRouter()


class HealthResponse(BaseModel):
    """
    Standardized health check response payload.
    """
    status: str = Field(..., description="Overall service status ('healthy' or 'unhealthy')")
    database: str = Field(..., description="Database connection status ('connected' or 'disconnected')")
    environment: str = Field(..., description="Deployment environment")
    error: Optional[str] = Field(None, description="Error detail if database connection fails")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    description="Verifies the operational status of the service and validates PostgreSQL database connectivity using SELECT 1.",
    responses={
        200: {
            "description": "Service and database are healthy and accepting traffic.",
            "model": HealthResponse,
        },
        503: {
            "description": "Database is unreachable or failed the connectivity check.",
            "model": HealthResponse,
        },
    },
)
def get_health(
    response: Response,
    db: Session = Depends(get_db),
) -> HealthResponse:
    """
    Executes SELECT 1 against the PostgreSQL database.
    Returns 200 OK when connected, or 503 Service Unavailable on failure.
    """
    is_connected, error_message = check_db_connection(db)

    if not is_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="unhealthy",
            database="disconnected",
            environment=settings.ENVIRONMENT,
            error=error_message,
        )

    return HealthResponse(
        status="healthy",
        database="connected",
        environment=settings.ENVIRONMENT,
        error=None,
    )
