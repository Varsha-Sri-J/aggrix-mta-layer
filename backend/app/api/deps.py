"""
FastAPI Authentication & RBAC Dependencies.

Provides reusable dependencies for:
- Token extraction and current user verification.
- Tenant analytics authorization with role-based checks.
- Manager assigned-tenant retrieval.
- Platform administrator authorization.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, Path, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.connection import get_db
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.tenant import Tenant
from app.models.user import User, UserRole

# HTTP Bearer authentication scheme (auto_error=False to provide tailored 401 messages)
security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    token_query: Optional[str] = Query(None, alias="token", description="Optional JWT bearer token query param for SSE EventSource"),
    db: Session = Depends(get_db),
) -> User:
    """
    Extracts and cryptographically validates the JWT bearer token from the Authorization header
    or query parameter 'token' (enabling native browser EventSource connections).
    Returns the authenticated active User object.
    Raises 401 Unauthorized on missing, invalid, or expired tokens.
    Raises 403 Forbidden on inactive user accounts.
    """
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif token_query:
        token = token_query

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject claim is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user ID claim in token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


def get_authorized_tenant(
    tenant_id: uuid.UUID = Path(..., description="Target tenant UUID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Tenant:
    """
    Validates that the authenticated user possesses authorization to access analytics for {tenant_id}.
    Enforces RBAC:
    - Platform Admin: Access allowed for all tenants.
    - Multi-Store Manager: Access allowed ONLY if tenant_id is explicitly assigned.
    - Tenant User: Access allowed ONLY if tenant_id matches their own home tenant.
    Never trusts tenant_id from client without checking permissions.
    Returns the verified Tenant object or raises 403 Forbidden / 404 Not Found.
    """
    # 1. Verify tenant exists in the database
    tenant = db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID '{tenant_id}' not found.",
        )

    # 2. Enforce RBAC permissions
    if current_user.role == UserRole.PLATFORM_ADMIN.value:
        return tenant

    if current_user.role == UserRole.STORE_MANAGER.value:
        # Check explicit manager assignment
        assignment = db.execute(
            select(ManagerTenantAssignment).where(
                ManagerTenantAssignment.user_id == current_user.id,
                ManagerTenantAssignment.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: store manager is not assigned to this tenant.",
            )
        return tenant

    if current_user.role == UserRole.TENANT_USER.value:
        # Check tenant user home tenant match
        if current_user.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: tenant users can only access their own tenant data.",
            )
        return tenant

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: unrecognized user role.",
    )


def get_manager_assigned_tenant_ids(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[uuid.UUID]:
    """
    Retrieves the list of authorized tenant IDs for a manager or platform administrator.
    Raises 403 Forbidden for tenant users.
    """
    if current_user.role == UserRole.TENANT_USER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: multi-store manager or platform administrator role required.",
        )

    if current_user.role == UserRole.STORE_MANAGER.value:
        # Retrieve explicit assignments
        stmt = select(ManagerTenantAssignment.tenant_id).where(
            ManagerTenantAssignment.user_id == current_user.id
        )
        return list(db.execute(stmt).scalars().all())

    if current_user.role == UserRole.PLATFORM_ADMIN.value:
        # Platform admin has access to all tenants
        stmt = select(Tenant.id)
        return list(db.execute(stmt).scalars().all())

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: unrecognized user role.",
    )


def require_platform_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Restricts access strictly to Platform Administrators.
    Raises 403 Forbidden for tenant users and store managers.
    """
    if current_user.role != UserRole.PLATFORM_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: platform administrator privileges required.",
        )
    return current_user
