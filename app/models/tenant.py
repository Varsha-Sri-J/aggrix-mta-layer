"""Tenant SQLAlchemy 2.0 Model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order import Order
    from app.models.order_item import OrderItem
    from app.models.outbox_event import OutboxEvent
    from app.models.product import Product


class Tenant(Base):
    """Represents a store/organization in AGGRIX's multi-tenant architecture."""

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_tenants_domain"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for the tenant.",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable business or store name.",
    )
    domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Unique domain/subdomain representing the store (e.g. store.myshopify.com).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the tenant was onboarded.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when the tenant record was last modified.",
    )

    # Relationships to child entities owned by this tenant
    customers: Mapped[list["Customer"]] = relationship(
        "Customer",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    products: Mapped[list["Product"]] = relationship(
        "Product",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    order_items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True,
        overlaps="items,order",
    )
    outbox_events: Mapped[list["OutboxEvent"]] = relationship(
        "OutboxEvent",
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
