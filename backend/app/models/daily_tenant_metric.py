"""DailyTenantMetric SQLAlchemy 2.0 Model."""
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class DailyTenantMetric(Base):
    """Historical daily aggregation rollups per tenant and currency."""

    __tablename__ = "daily_tenant_metrics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_daily_tenant_metrics_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "metric_date",
            "currency",
            name="uq_daily_tenant_metrics_tenant_date_currency",
        ),
        CheckConstraint("orders_count >= 0", name="orders_non_negative"),
        CheckConstraint("gross_sales >= 0", name="gross_non_negative"),
        CheckConstraint("net_sales >= 0", name="net_non_negative"),
        CheckConstraint("pending_orders_count >= 0", name="pending_orders_non_negative"),
        CheckConstraint("pending_sales >= 0", name="pending_sales_non_negative"),
        CheckConstraint(
            "cancelled_orders_count >= 0",
            name="cancelled_orders_non_negative",
        ),
        CheckConstraint(
            "cancelled_sales >= 0",
            name="cancelled_sales_non_negative",
        ),
        Index("ix_daily_tenant_metrics_tenant_date", "tenant_id", "metric_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique internal identifier for the daily tenant metric record.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the owning tenant.",
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
    orders_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Total number of orders placed on this calendar date.",
    )
    gross_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Gross monetary sales value of all orders placed on this date.",
    )
    net_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Net monetary sales value excluding cancelled orders.",
    )
    pending_orders_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Count of orders placed on this date that are currently pending payment.",
    )
    pending_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Monetary sales value of orders placed on this date that are currently pending payment.",
    )
    cancelled_orders_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Count of orders placed on this date that were cancelled.",
    )
    cancelled_sales: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
        doc="Monetary sales value of orders placed on this date that were cancelled.",
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

    tenant: Mapped["Tenant"] = relationship("Tenant")
