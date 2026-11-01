"""DailyProductMetric SQLAlchemy 2.0 Model."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.tenant import Tenant


class DailyProductMetric(Base):
    """Historical daily aggregation rollups per product, tenant, and currency."""

    __tablename__ = "daily_product_metrics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_daily_product_metrics_tenant_id",
        ),
        # Tenant-aware composite foreign key ensures product belongs strictly to the same tenant.
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            ondelete="CASCADE",
            name="fk_daily_product_metrics_product_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "product_id",
            "metric_date",
            "currency",
            name="uq_daily_product_metrics_tenant_product_date_currency",
        ),
        CheckConstraint(
            "units_sold_gross >= 0",
            name="gross_units_non_negative",
        ),
        CheckConstraint(
            "units_sold_net >= 0",
            name="net_units_non_negative",
        ),
        CheckConstraint(
            "gross_sales >= 0",
            name="gross_sales_non_negative",
        ),
        CheckConstraint(
            "net_sales >= 0",
            name="net_sales_non_negative",
        ),
        CheckConstraint(
            "pending_units >= 0",
            name="pending_units_non_negative",
        ),
        CheckConstraint(
            "pending_sales >= 0",
            name="pending_sales_non_negative",
        ),
        CheckConstraint(
            "cancelled_units >= 0",
            name="cancelled_units_non_negative",
        ),
        CheckConstraint(
            "cancelled_sales >= 0",
            name="cancelled_sales_non_negative",
        ),
        CheckConstraint(
            "orders_count >= 0",
            name="orders_count_non_negative",
        ),
        Index("ix_daily_product_metrics_tenant_date", "tenant_id", "metric_date"),
        Index(
            "ix_daily_product_metrics_tenant_product_date",
            "tenant_id",
            "product_id",
            "metric_date",
        ),
        Index("ix_daily_product_metrics_tenant_product", "tenant_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique internal identifier for the daily product metric record.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the owning tenant.",
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the product catalog item.",
    )
    metric_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        doc="Calendar date of the metric rollup in tenant reporting timezone.",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
        doc="ISO 4217 three-letter currency code (e.g. INR, USD).",
    )
    units_sold_gross: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Total units ordered on this calendar date.",
    )
    units_sold_net: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Net units sold excluding cancelled orders.",
    )
    gross_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Gross monetary sales value of this product on this date.",
    )
    net_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Net monetary sales value of this product excluding cancellations.",
    )
    pending_units: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Count of units belonging to pending orders placed on this date.",
    )
    pending_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Monetary sales value of units belonging to pending orders placed on this date.",
    )
    cancelled_units: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Count of units cancelled for orders placed on this date.",
    )
    cancelled_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Monetary sales value of cancelled units for orders placed on this date.",
    )
    orders_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Distinct count of orders containing this product placed on this date.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when this metric record was created.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when this metric record was last updated or recalculated.",
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", foreign_keys=[tenant_id])
    product: Mapped["Product"] = relationship(
        "Product",
        primaryjoin="and_(Product.tenant_id == DailyProductMetric.tenant_id, Product.id == foreign(DailyProductMetric.product_id))",
        overlaps="tenant",
    )
