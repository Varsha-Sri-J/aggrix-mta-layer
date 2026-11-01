"""
Order Ingestion API Routes.

Provides authenticated, tenant-isolated REST endpoints for merchants, managers,
and platform administrators to ingest transactional order data into AGGRIX.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.ingestion import OrderIngestionService
from app.api.deps import get_current_user, get_db
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.schemas.ingest import (
    OrderBatchIngestPayload,
    OrderBatchIngestResponse,
    OrderIngestPayload,
    OrderIngestResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_target_tenant_id(
    target_tenant_id: Optional[uuid.UUID],
    current_user: User,
    db: Session,
) -> uuid.UUID:
    """
    Validates and resolves the target tenant UUID for ingestion based on user RBAC.
    Enforces strict tenant isolation and prevents cross-tenant data injection.
    """
    if current_user.role == UserRole.TENANT_USER.value:
        if not current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Merchant user has no associated tenant ID.",
            )
        # If payload specifies a tenant_id, it MUST match the user's home tenant
        if target_tenant_id and target_tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant ingestion forbidden: merchant users may only ingest orders for their assigned tenant.",
            )
        target_id = current_user.tenant_id

    elif current_user.role == UserRole.STORE_MANAGER.value:
        if not target_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store managers must explicitly specify target 'tenant_id'.",
            )
        # Verify manager is explicitly assigned to this store
        assignment = db.execute(
            select(ManagerTenantAssignment).where(
                ManagerTenantAssignment.user_id == current_user.id,
                ManagerTenantAssignment.tenant_id == target_tenant_id,
            )
        ).scalar_one_or_none()
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: manager is not assigned to store '{target_tenant_id}'.",
            )
        target_id = target_tenant_id

    elif current_user.role == UserRole.PLATFORM_ADMIN.value:
        if not target_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Platform admins must explicitly specify target 'tenant_id'.",
            )
        target_id = target_tenant_id

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unrecognized user role.",
        )

    # Verify tenant exists
    tenant = db.execute(select(Tenant).where(Tenant.id == target_id)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{target_id}' not found.",
        )

    return target_id


@router.post(
    "/orders",
    response_model=OrderIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a Single Merchant Order",
    description=(
        "Ingests a live merchant order, persists customer, product, order, and line items, "
        "and atomically publishes an outbox event for incremental aggregation processing."
    ),
)
def ingest_single_order(
    payload: OrderIngestPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderIngestResponse:
    """Ingests a single merchant order with strict tenant isolation and validation."""
    target_tenant_id = _resolve_target_tenant_id(
        target_tenant_id=payload.tenant_id,
        current_user=current_user,
        db=db,
    )

    service = OrderIngestionService(db=db)
    return service.ingest_order(tenant_id=target_tenant_id, payload=payload)


@router.post(
    "/orders/batch",
    response_model=OrderBatchIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a Batch of Merchant Orders",
    description="Ingests multiple merchant orders in a single payload scoped to an authorized tenant.",
)
def ingest_batch_orders(
    payload: OrderBatchIngestPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderBatchIngestResponse:
    """Ingests a batch of orders with strict tenant isolation and validation."""
    target_tenant_id = _resolve_target_tenant_id(
        target_tenant_id=payload.tenant_id,
        current_user=current_user,
        db=db,
    )

    service = OrderIngestionService(db=db)
    return service.ingest_batch(tenant_id=target_tenant_id, payload=payload)
