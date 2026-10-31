"""OutboxEvent SQLAlchemy 2.0 Model."""

import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class OutboxEvent(Base):
    """Transactional outbox table for reliable domain event publishing across tenants."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_outbox_events_tenant_id",
        ),
        Index("ix_outbox_events_tenant_id", "tenant_id"),
        # Partial index for lightning-fast polling of unprocessed outbox events in PostgreSQL.
        Index(
            "ix_outbox_events_unprocessed",
            "created_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
        Index("ix_outbox_events_processed_at", "processed_at"),
        Index("ix_outbox_events_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for the outbox event.",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        doc="Foreign key referencing the owning tenant.",
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Classification of the event (e.g. order.created, customer.registered).",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        doc="Structured event data stored as native PostgreSQL JSONB.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the event was recorded in the database.",
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        doc="Timestamp when the event was successfully processed/published (None if pending).",
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="outbox_events")

