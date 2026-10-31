"""Pydantic v2 schemas for Authentication & RBAC."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.user import UserRole


class LoginRequest(BaseModel):
    """Payload for user authentication. Supports both 'email' and 'username' fields."""

    email: Optional[str] = Field(None, max_length=255, description="Registered email address")
    username: Optional[str] = Field(None, max_length=255, description="Alternative username/email field")
    password: str = Field(..., min_length=1, description="Account password")

    @model_validator(mode="before")
    @classmethod
    def validate_email_or_username(cls, data: Any) -> Any:
        if isinstance(data, dict):
            email_val = data.get("email") or data.get("username")
            if not email_val or not str(email_val).strip():
                raise ValueError("Email address or username must be provided.")
            data["email"] = str(email_val).strip()
        return data


class TokenResponse(BaseModel):
    """Bearer token response payload."""

    access_token: str = Field(..., description="Cryptographically signed JWT bearer token")
    token_type: str = Field(default="bearer", description="Token type identifier")
    user_id: uuid.UUID = Field(..., description="Authenticated user ID")
    email: str = Field(..., description="Authenticated user email")
    role: str = Field(..., description="Assigned RBAC role")
    tenant_id: Optional[uuid.UUID] = Field(None, description="Home tenant UUID (for tenant users)")
    assigned_tenant_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="List of explicitly assigned tenant UUIDs (for store managers)",
    )
    # Frontend compatibility fields
    tenant_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="Alias for assigned_tenant_ids for frontend compatibility",
    )


class UserResponse(BaseModel):
    """User profile response representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="User unique identifier")
    email: str = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, description="Display name")
    role: str = Field(..., description="RBAC role")
    is_active: bool = Field(..., description="Account status")
    tenant_id: Optional[uuid.UUID] = Field(None, description="Home tenant identifier")
    assigned_tenant_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="Assigned tenant store IDs",
    )
    created_at: datetime = Field(..., description="Registration timestamp")
    # Frontend compatibility fields
    active_tenant_id: Optional[uuid.UUID] = Field(
        None,
        description="Alias for tenant_id for frontend compatibility",
    )
    assigned_tenants: List[uuid.UUID] = Field(
        default_factory=list,
        description="Alias for assigned_tenant_ids for frontend compatibility",
    )


class UserRegisterRequest(BaseModel):
    """
    Public registration request schema.
    Strictly forbids role selection, arbitrary tenant assignment, and manager store assignments.
    """

    email: str = Field(..., max_length=255, description="Registered email address")
    password: str = Field(..., min_length=8, description="Account password (minimum 8 characters)")
    full_name: Optional[str] = Field(None, description="User display name")


# Backward compatibility alias
UserCreateRequest = UserRegisterRequest


class UserProvisionRequest(BaseModel):
    """
    Protected provisioning request schema for Platform Administrators.
    Allows authorized administrators to provision tenant users, managers, and admins.
    """

    email: str = Field(..., max_length=255, description="User email address")
    password: str = Field(..., min_length=8, description="Initial plaintext password (minimum 8 characters)")
    full_name: Optional[str] = Field(None, description="User display name")
    role: UserRole = Field(..., description="Assigned RBAC role (tenant_user, store_manager, platform_admin)")
    tenant_id: Optional[uuid.UUID] = Field(
        None,
        description="Home tenant UUID. Required when role is 'tenant_user'; must be None for other roles.",
    )
    assigned_tenant_ids: Optional[List[uuid.UUID]] = Field(
        None,
        description="Explicit assigned store UUIDs. Only valid when role is 'store_manager'; must be None for other roles.",
    )

