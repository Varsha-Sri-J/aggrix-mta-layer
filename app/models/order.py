"""Order SQLAlchemy 2.0 Model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order_item import OrderItem
    from app.models.tenant import Tenant


class Order(Base):
    """E-commerce order entity with tenant-isolated customer references."""

    __tablename__ = "orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_orders_tenant_id",
        ),
        # Composite foreign key ensures that an order can ONLY reference a customer
        # that belongs to the exact same tenant. Cross-tenant customer references are
        # physically rejected by the database.
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
            name="fk_orders_customer_tenant",
        ),
        # Unique constraint on (tenant_id, id) is required as the target of the composite
        # foreign key constraint from order_items.
        UniqueConstraint("tenant_id", "id", name="uq_orders_tenant_id_id"),
        # External order ID (e.g. Shopify #1001) is unique within a tenant store.
        UniqueConstraint(
            "tenant_id",
            "external_order_id",
            name="uq_orders_tenant_id_external_order_id",
        ),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
        Index("ix_orders_tenant_id", "tenant_id"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
        Index("ix_orders_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_orders_tenant_status_created_at", "tenant_id", "status", "created_at"),
        Index("ix_orders_tenant_customer_id", "tenant_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique internal order identifier.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the owning tenant.",
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the customer (co-referenced with tenant_id).",
    )
    external_order_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="External identifier from the source e-commerce platform (e.g. Shopify order id).",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        doc="Total monetary value of the order.",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
        server_default="USD",
        doc="ISO 4217 three-letter currency code.",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
        doc="Current status of the order (e.g. pending, paid, fulfilled, cancelled).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the order was placed or recorded.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when the order record was last updated.",
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="orders")
    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="orders",
        primaryjoin="and_(Customer.tenant_id == Order.tenant_id, Customer.id == foreign(Order.customer_id))",
        overlaps="tenant,orders",
    )
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        primaryjoin="and_(Order.tenant_id == OrderItem.tenant_id, Order.id == foreign(OrderItem.order_id))",
        overlaps="tenant,order_items",
    )

