"""
AGGRIX Authentication Routes.

Endpoints:
- POST /api/v1/auth/login: Authenticates user credentials and returns cryptographically signed JWT.
- GET /api/v1/auth/me: Returns current authenticated user profile and roles.
- POST /api/v1/auth/register: Registers a new user account with role assignment (tenant_user, store_manager, platform_admin).
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_admin
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.database.connection import get_db
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UserCreateRequest,
    UserProvisionRequest,
    UserRegisterRequest,
    UserResponse,
)

router = APIRouter()



@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Login",
    description="Authenticates email and password, returning a signed JWT bearer token.",
    responses={
        200: {"description": "Authentication successful."},
        401: {"description": "Invalid email or password."},
        403: {"description": "Account is deactivated."},
    },
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticates credentials against bcrypt password hashes and returns JWT."""
    stmt = select(User).where(User.email == payload.email)
    user = db.execute(stmt).scalar_one_or_none()

    if user is None:
        # Constant-time dummy verification neutralizes account enumeration timing side-channels
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )


    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    # If manager, query assigned tenants
    assigned_tenant_ids: List[uuid.UUID] = []
    if user.role == UserRole.STORE_MANAGER.value:
        assign_stmt = select(ManagerTenantAssignment.tenant_id).where(
            ManagerTenantAssignment.user_id == user.id
        )
        assigned_tenant_ids = list(db.execute(assign_stmt).scalars().all())

    access_token = create_access_token(
        subject=user.id,
        role=user.role,
        tenant_id=user.tenant_id,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        assigned_tenant_ids=assigned_tenant_ids,
        tenant_ids=assigned_tenant_ids,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current User Profile",
    description="Returns profile information and assigned store associations for the authenticated user.",
)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Returns authenticated user identity and roles."""
    assigned_ids: List[uuid.UUID] = []
    if current_user.role == UserRole.STORE_MANAGER.value:
        stmt = select(ManagerTenantAssignment.tenant_id).where(
            ManagerTenantAssignment.user_id == current_user.id
        )
        assigned_ids = list(db.execute(stmt).scalars().all())

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        tenant_id=current_user.tenant_id,
        assigned_tenant_ids=assigned_ids,
        active_tenant_id=current_user.tenant_id,
        assigned_tenants=assigned_ids,
        created_at=current_user.created_at,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_403_FORBIDDEN,
    summary="Public User Registration (Disabled)",
    description=(
        "Public self-registration is disabled for security. "
        "User accounts must be securely provisioned by an authorized Platform Administrator."
    ),
    responses={
        403: {"description": "Public registration is disabled."},
    },
)
def register_user(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Rejects anonymous self-registration attempts to prevent privilege escalation."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public self-registration is disabled. Accounts must be provisioned by an authorized platform administrator.",
    )


@router.post(
    "/provision",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision Authorized User Account",
    description=(
        "Securely provisions a new user account with specified RBAC role and store assignments. "
        "Accessible exclusively by Platform Administrators."
    ),
    responses={
        201: {"description": "User account successfully provisioned."},
        400: {"description": "Invalid provisioning payload, duplicate email, or missing/invalid tenant associations."},
        401: {"description": "Missing or invalid authentication token."},
        403: {"description": "Forbidden: platform administrator privileges required."},
    },
)
def provision_user(
    payload: UserProvisionRequest,
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Secure account provisioning endpoint restricted strictly to platform administrators.
    Enforces RBAC validation and relational constraints across roles.
    """
    # 1. Check email uniqueness
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{payload.email}' already exists.",
        )

    # 2. Validate role-specific parameters
    if payload.role == UserRole.TENANT_USER:
        if not payload.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant_id is required for tenant_user role.",
            )
        if payload.assigned_tenant_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="assigned_tenant_ids cannot be specified for tenant_user role.",
            )
        tenant_exists = db.execute(
            select(Tenant).where(Tenant.id == payload.tenant_id)
        ).scalar_one_or_none()
        if not tenant_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target tenant '{payload.tenant_id}' does not exist.",
            )

    elif payload.role == UserRole.STORE_MANAGER:
        if payload.tenant_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant_id cannot be specified for store_manager role; use assigned_tenant_ids.",
            )

    elif payload.role == UserRole.PLATFORM_ADMIN:
        if payload.tenant_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant_id cannot be specified for platform_admin role.",
            )
        if payload.assigned_tenant_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="assigned_tenant_ids cannot be specified for platform_admin role.",
            )

    # 3. Create the user entity
    new_user = User(
        id=uuid.uuid4(),
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role.value,
        is_active=True,
        tenant_id=payload.tenant_id if payload.role == UserRole.TENANT_USER else None,
    )
    db.add(new_user)
    db.flush()

    # 4. Process manager store assignments
    assigned_ids: List[uuid.UUID] = []
    if payload.role == UserRole.STORE_MANAGER and payload.assigned_tenant_ids:
        # Deduplicate assigned tenant IDs
        unique_tenant_ids = list(dict.fromkeys(payload.assigned_tenant_ids))
        for t_id in unique_tenant_ids:
            t_exists = db.execute(select(Tenant).where(Tenant.id == t_id)).scalar_one_or_none()
            if not t_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Assigned tenant '{t_id}' does not exist.",
                )
            assignment = ManagerTenantAssignment(
                id=uuid.uuid4(),
                user_id=new_user.id,
                user_role=new_user.role,
                tenant_id=t_id,
            )
            db.add(assignment)
            assigned_ids.append(t_id)

    db.commit()
    db.refresh(new_user)

    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role,
        is_active=new_user.is_active,
        tenant_id=new_user.tenant_id,
        assigned_tenant_ids=assigned_ids,
        created_at=new_user.created_at,
    )


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision Authorized User Account (Alias)",
    include_in_schema=False,
)
def provision_user_alias(
    payload: UserProvisionRequest,
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Alias for /provision endpoint."""
    return provision_user(payload=payload, admin_user=admin_user, db=db)

