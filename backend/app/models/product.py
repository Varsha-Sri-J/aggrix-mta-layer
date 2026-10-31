"""Product SQLAlchemy 2.0 Model."""

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
    from app.models.order_item import OrderItem
    from app.models.tenant import Tenant


class Product(Base):
    """Product catalog item scoped to a specific tenant."""

    __tablename__ = "products"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_products_tenant_id",
        ),
        # Unique constraint on (tenant_id, id) is required as the target of the composite
        # foreign key constraint from the order_items table.
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
        # SKU uniqueness is strictly scoped to the tenant (different tenants can use the same SKU).
        UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_id_sku"),
        CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        Index("ix_products_tenant_id", "tenant_id"),
        Index("ix_products_sku", "sku"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique product identifier.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the owning tenant.",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Name of the product.",
    )
    sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Stock Keeping Unit (unique per tenant).",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        doc="Unit selling price (must be non-negative).",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
        server_default="USD",
        doc="ISO 4217 three-letter currency code (e.g. USD, EUR, GBP).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the product was cataloged.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when the product was last modified.",
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="products")
    order_items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="product",
        primaryjoin="and_(Product.tenant_id == OrderItem.tenant_id, Product.id == foreign(OrderItem.product_id))",
        overlaps="tenant,order_items",
    )

