"""ManagerTenantAssignment SQLAlchemy 2.0 Model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    from app.models.tenant import Tenant
    from app.models.user import User


class ManagerTenantAssignment(Base):
    """
    Explicit assignment mapping multi-store managers to authorized tenant stores.
    Enforces that store managers can only query analytics for explicitly assigned tenants.
    Relational constraints enforce that only users with role='store_manager' can receive assignments.
    """

    __tablename__ = "manager_tenant_assignments"
    __table_args__ = (
        CheckConstraint(
            "user_role = 'store_manager'",
            name="ck_manager_tenant_assignments_role_is_manager",
        ),
        ForeignKeyConstraint(
            ["user_id", "user_role"],
            ["users.id", "users.role"],
            ondelete="CASCADE",
            name="fk_manager_tenant_assignments_user_role",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_manager_tenant_assignments_user_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_manager_tenant_assignments_tenant_id",
        ),
        UniqueConstraint(
            "user_id",
            "tenant_id",
            name="uq_manager_tenant_assignments_user_tenant",
        ),
        Index("ix_manager_tenant_assignments_user_tenant", "user_id", "tenant_id"),
        Index("ix_manager_tenant_assignments_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for the manager-tenant assignment record.",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the multi-store manager user.",
    )
    user_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="store_manager",
        server_default="store_manager",
        doc="Role of the assigned user. Relational constraint verifies users.role is 'store_manager'.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the assigned tenant store.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the assignment was granted.",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="manager_assignments",
        foreign_keys=[user_id],
    )
    tenant: Mapped["Tenant"] = relationship("Tenant")

