"""AnalyticsDeadLetterEvent SQLAlchemy 2.0 Model.

Captures permanently malformed or repeatedly failing outbox events, providing
isolated dead-letter queue (DLQ) tracking, retry counting, and error diagnostics
without blocking the incremental aggregation worker pipeline.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class AnalyticsDeadLetterEvent(Base):
    """Quarantine table for events that exceed maximum retry attempts or fail aggregation."""

    __tablename__ = "analytics_dead_letter_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_analytics_dead_letter_tenant_id",
        ),
        ForeignKeyConstraint(
            ["event_id"],
            ["outbox_events.id"],
            ondelete="CASCADE",
            name="fk_analytics_dead_letter_event_id",
        ),
        UniqueConstraint(
            "consumer_name",
            "event_id",
            name="uq_analytics_dead_letter_consumer_event",
        ),
        Index(
            "ix_analytics_dead_letter_consumer_tenant",
            "consumer_name",
            "tenant_id",
            "last_failed_at",
        ),
        Index(
            "ix_analytics_dead_letter_consumer_attempts",
            "consumer_name",
            "attempts",
        ),
        Index(
            "ix_analytics_dead_letter_event_id",
            "event_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique dead-letter record identifier.",
    )
    consumer_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="analytics_worker",
        doc="Name of the consumer that failed to process the event.",
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="UUID of the outbox event that failed.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Owning tenant identifier.",
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Event type (e.g. order.created, order.paid).",
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
        doc="Order identifier if extractable from payload.",
    )
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Primary error message or exception string.",
    )
    error_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        doc="Structured diagnostics, payload snippet, or exception type.",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        default=1,
        doc="Total number of failed processing attempts.",
    )
    first_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp of first failure attempt.",
    )
    last_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp of most recent failure attempt.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Record creation timestamp.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Record update timestamp.",
    )

    # Relationships
    tenant: Mapped[Tenant] = relationship(
        "Tenant",
        lazy="joined",
    )
