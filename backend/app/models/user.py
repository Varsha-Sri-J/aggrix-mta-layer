"""User SQLAlchemy 2.0 Model."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.manager_tenant_assignment import ManagerTenantAssignment
    from app.models.tenant import Tenant


class UserRole(str, enum.Enum):
    """Supported authorization roles in AGGRIX."""
    TENANT_USER = "tenant_user"
    STORE_MANAGER = "store_manager"
    PLATFORM_ADMIN = "platform_admin"


class User(Base):
    """
    User entity representing system actors (Tenant Staff, Store Managers, Platform Admins).
    """

    __tablename__ = "users"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="SET NULL",
            name="fk_users_tenant_id",
        ),
        CheckConstraint(
            "role IN ('tenant_user', 'store_manager', 'platform_admin')",
            name="ck_users_role_valid",
        ),
        UniqueConstraint("id", "role", name="uq_users_id_role"),
        Index("ix_users_role", "role"),
        Index("ix_users_tenant_id", "tenant_id"),
    )


    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique user identifier.",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique email address used for authentication.",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Cryptographically secure bcrypt password hash.",
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Display name of the user.",
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=UserRole.TENANT_USER.value,
        server_default=UserRole.TENANT_USER.value,
        doc="Assigned RBAC role (tenant_user, store_manager, platform_admin).",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="Account operational status flag.",
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
        doc="Home tenant UUID for tenant_user role (nullable for platform_admin or store_manager).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when user was created.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when user was last updated.",
    )

    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", foreign_keys=[tenant_id])
    manager_assignments: Mapped[List["ManagerTenantAssignment"]] = relationship(
        "ManagerTenantAssignment",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ManagerTenantAssignment.user_id",
    )

