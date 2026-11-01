"""
Pydantic Schemas for Live Order Ingestion.

Supports single-order and batch ingestion of merchant transactions.
Validates monetary constraints, tenant scopes, line items, and lifecycle states.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerIngestPayload(BaseModel):
    """Customer profile metadata submitted alongside an order."""
    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(..., description="Customer primary email address")
    name: Optional[str] = Field(None, max_length=255, description="Customer full name")


class OrderItemIngestPayload(BaseModel):
    """Line item itemization for an ingested order."""
    model_config = ConfigDict(from_attributes=True)

    sku: str = Field(..., min_length=1, max_length=100, description="Product catalog SKU")
    name: Optional[str] = Field(None, max_length=255, description="Product catalog display name")
    quantity: int = Field(..., ge=1, description="Quantity of units ordered (>= 1)")
    unit_price: Decimal = Field(..., ge=0, description="Unit price per item (>= 0)")


class OrderIngestPayload(BaseModel):
    """Payload for ingesting a single merchant order."""
    model_config = ConfigDict(from_attributes=True)

    tenant_id: Optional[uuid.UUID] = Field(
        None,
        description="Target tenant UUID (optional; defaults to authenticated tenant user's home store)",
    )
    external_order_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Source e-commerce platform external order identifier (e.g. #1001)",
    )
    customer: CustomerIngestPayload = Field(
        ...,
        description="Customer profile details",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="ISO 4217 3-letter currency code",
    )
    status: str = Field(
        default="pending",
        pattern=r"^(pending|paid|fulfilled|cancelled)$",
        description="Current order status: pending, paid, fulfilled, cancelled",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="Timestamp when the transaction occurred (defaults to now)",
    )
    items: List[OrderItemIngestPayload] = Field(
        ...,
        min_length=1,
        description="Itemized list of order line items (at least one item required)",
    )
    total_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Total monetary value (defaults to sum of items * unit_price)",
    )


class OrderIngestResponse(BaseModel):
    """Response returned upon successfully ingesting an order transaction."""
    model_config = ConfigDict(from_attributes=True)

    order_id: uuid.UUID
    tenant_id: uuid.UUID
    external_order_id: str
    status: str
    currency: str
    total_amount: Decimal
    items_count: int
    outbox_event_id: uuid.UUID
    event_type: str
    is_duplicate: bool = False
    message: str


class OrderBatchIngestPayload(BaseModel):
    """Payload for submitting a batch of orders for a merchant."""
    model_config = ConfigDict(from_attributes=True)

    tenant_id: Optional[uuid.UUID] = Field(None, description="Target tenant UUID")
    orders: List[OrderIngestPayload] = Field(..., min_length=1, max_length=500, description="List of orders to ingest")


class OrderBatchIngestResponse(BaseModel):
    """Response returned upon processing an order batch."""
    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    total_submitted: int
    ingested_count: int
    duplicate_count: int
    orders: List[OrderIngestResponse]
