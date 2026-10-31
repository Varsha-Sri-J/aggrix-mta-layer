"""AnalyticsConsumerEvent SQLAlchemy 2.0 Model.

Provides isolated, consumer-specific event tracking and deduplication for the
AGGRIX analytics aggregation engine without mutating shared transactional outbox tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class AnalyticsConsumerEvent(Base):
    """Consumer-specific tracking table ensuring idempotent, once-only event processing."""

    __tablename__ = "analytics_consumer_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_analytics_consumer_events_tenant_id",
        ),
        Index(
            "ix_analytics_consumer_events_consumer_tenant",
            "consumer_name",
            "tenant_id",
            "processed_at",
        ),
        Index(
            "ix_analytics_consumer_events_consumer_order",
            "consumer_name",
            "order_id",
        ),
    )

    consumer_name: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        default="analytics_worker",
        doc="Name of the downstream consumer (e.g. analytics_worker).",
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        doc="UUID of the outbox event that was processed.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Owning tenant identifier.",
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Event type classification (e.g. order.created, order.paid).",
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Associated order identifier.",
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when this consumer processed the event.",
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", foreign_keys=[tenant_id])
