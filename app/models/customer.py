"""Customer SQLAlchemy 2.0 Model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.tenant import Tenant


class Customer(Base):
    """Customer profile scoped to a specific tenant."""

    __tablename__ = "customers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_customers_tenant_id",
        ),
        # Unique constraint on (tenant_id, id) is required to serve as the target
        # of the composite foreign key from the orders table.
        UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id_id"),
        # Customer email is uniquely scoped per tenant (two stores can have the same customer email).
        UniqueConstraint("tenant_id", "email", name="uq_customers_tenant_id_email"),
        Index("ix_customers_tenant_id", "tenant_id"),
        Index("ix_customers_email", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique customer identifier.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key to the owning tenant.",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Customer email address (unique within the tenant).",
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Full name or display name of the customer.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the customer profile was created.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when the customer profile was last updated.",
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="customers")
    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="customer",
        primaryjoin="and_(Customer.tenant_id == Order.tenant_id, Customer.id == foreign(Order.customer_id))",
        overlaps="tenant,orders",
    )

