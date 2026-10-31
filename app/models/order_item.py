"""OrderItem SQLAlchemy 2.0 Model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.product import Product
    from app.models.tenant import Tenant


class OrderItem(Base):
    """Line item within an order, protected by composite foreign keys to order and product."""

    __tablename__ = "order_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_order_items_tenant_id",
        ),
        # Composite foreign key ensures the order item CANNOT reference an order from another tenant.
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            ondelete="CASCADE",
            name="fk_order_items_order_tenant",
        ),
        # Composite foreign key ensures the order item CANNOT reference a product from another tenant.
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            ondelete="RESTRICT",
            name="fk_order_items_product_tenant",
        ),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
        Index("ix_order_items_tenant_id", "tenant_id"),
        Index("ix_order_items_tenant_order_id", "tenant_id", "order_id"),
        Index("ix_order_items_tenant_product_id", "tenant_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for the order line item.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the owning tenant.",
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the parent order.",
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the purchased product.",
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Quantity purchased (strictly positive).",
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        doc="Price per unit at the time of purchase.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the order item was recorded.",
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="order_items",
        overlaps="items,order",
    )
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="items",
        primaryjoin="and_(Order.tenant_id == OrderItem.tenant_id, Order.id == foreign(OrderItem.order_id))",
        overlaps="items,order_items,tenant",
    )
    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="order_items",
        primaryjoin="and_(Product.tenant_id == OrderItem.tenant_id, Product.id == foreign(OrderItem.product_id))",
        overlaps="items,order,order_items,tenant",
    )

