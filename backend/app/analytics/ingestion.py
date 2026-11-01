"""
Order Ingestion Service for AGGRIX MTA Layer.

Provides transactional persistence of live merchant order and lifecycle events.
Guarantees tenant isolation, referential integrity via composite keys,
and atomic publishing to the transactional outbox (outbox_events) for live worker consumption.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.schemas.ingest import (
    OrderIngestPayload,
    OrderIngestResponse,
    OrderBatchIngestPayload,
    OrderBatchIngestResponse,
)

logger = logging.getLogger(__name__)


def _to_event_type(status: str) -> str:
    """Maps domain order status to supported outbox event type."""
    if status == "pending":
        return "order.created"
    return f"order.{status}"


class OrderIngestionService:
    """Service handling merchant order transaction ingestion and outbox event creation."""

    def __init__(self, db: Session):
        self.db = db

    def ingest_order(
        self,
        tenant_id: uuid.UUID,
        payload: OrderIngestPayload,
    ) -> OrderIngestResponse:
        """
        Ingests a single merchant order.
        Validates external_order_id uniqueness, links/creates customer & products,
        writes Order and OrderItem records, and publishes the outbox event atomically.
        """
        # 1. Calculate or validate total amount
        items_total = sum(
            (Decimal(str(item.quantity)) * Decimal(str(item.unit_price)) for item in payload.items),
            start=Decimal("0.00"),
        )
        total_amount = Decimal(str(payload.total_amount)) if payload.total_amount is not None else items_total

        # 2. Check for existing order with same external_order_id within this tenant
        existing_order = self.db.execute(
            select(Order).where(
                Order.tenant_id == tenant_id,
                Order.external_order_id == payload.external_order_id,
            )
        ).scalar_one_or_none()

        if existing_order:
            # Handle lifecycle transition if status has changed
            if existing_order.status != payload.status:
                old_status = existing_order.status
                existing_order.status = payload.status
                existing_order.updated_at = datetime.now(timezone.utc)

                # Emit lifecycle transition event
                transition_event_id = uuid.uuid4()
                transition_payload = {
                    "order_id": str(existing_order.id),
                    "tenant_id": str(tenant_id),
                    "customer_id": str(existing_order.customer_id),
                    "external_order_id": existing_order.external_order_id,
                    "status": payload.status,
                    "previous_status": old_status,
                    "currency": existing_order.currency,
                    "total_amount": str(existing_order.total_amount),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
                event_type = _to_event_type(payload.status)
                outbox_transition = OutboxEvent(
                    id=transition_event_id,
                    tenant_id=tenant_id,
                    event_type=event_type,
                    payload=transition_payload,
                    created_at=datetime.now(timezone.utc),
                )
                self.db.add(outbox_transition)
                self.db.commit()

                return OrderIngestResponse(
                    order_id=existing_order.id,
                    tenant_id=tenant_id,
                    external_order_id=existing_order.external_order_id,
                    status=existing_order.status,
                    currency=existing_order.currency,
                    total_amount=existing_order.total_amount,
                    items_count=len(payload.items),
                    outbox_event_id=transition_event_id,
                    event_type=event_type,
                    is_duplicate=False,
                    message=f"Order status transitioned from '{old_status}' to '{payload.status}' successfully.",
                )

            # Idempotent return for identical duplicate
            return OrderIngestResponse(
                order_id=existing_order.id,
                tenant_id=tenant_id,
                external_order_id=existing_order.external_order_id,
                status=existing_order.status,
                currency=existing_order.currency,
                total_amount=existing_order.total_amount,
                items_count=len(payload.items),
                outbox_event_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                event_type=f"order.{existing_order.status}",
                is_duplicate=True,
                message="Order with this external_order_id already exists with identical status (idempotent duplicate).",
            )

        # 3. Resolve or create tenant-scoped customer
        customer = self.db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.email == payload.customer.email,
            )
        ).scalar_one_or_none()

        if not customer:
            customer = Customer(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                email=payload.customer.email,
                name=payload.customer.name or payload.customer.email.split("@")[0].replace(".", " ").title(),
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(customer)
            self.db.flush()

        # 4. Create the Order entity
        order_created_at = payload.created_at or datetime.now(timezone.utc)
        order = Order(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=customer.id,
            external_order_id=payload.external_order_id,
            total_amount=total_amount,
            currency=payload.currency.upper(),
            status=payload.status,
            created_at=order_created_at,
            updated_at=order_created_at,
        )
        self.db.add(order)
        self.db.flush()

        # 5. Resolve products and create line items
        outbox_items = []
        for item in payload.items:
            product = self.db.execute(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.sku == item.sku,
                )
            ).scalar_one_or_none()

            if not product:
                product = Product(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    sku=item.sku,
                    name=item.name or f"Product {item.sku}",
                    price=item.unit_price,
                    currency=payload.currency.upper(),
                    created_at=datetime.now(timezone.utc),
                )
                self.db.add(product)
                self.db.flush()

            order_item = OrderItem(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
            self.db.add(order_item)

            outbox_items.append({
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
            })

        self.db.flush()

        # 6. Publish Transactional Outbox Event
        outbox_event_id = uuid.uuid4()
        event_type = _to_event_type(order.status)
        outbox_payload = {
            "order_id": str(order.id),
            "tenant_id": str(tenant_id),
            "customer_id": str(customer.id),
            "external_order_id": order.external_order_id,
            "status": order.status,
            "currency": order.currency,
            "total_amount": str(order.total_amount),
            "created_at": order_created_at.isoformat(),
            "occurred_at": order_created_at.isoformat(),
            "items": outbox_items,
        }

        outbox_event = OutboxEvent(
            id=outbox_event_id,
            tenant_id=tenant_id,
            event_type=event_type,
            payload=outbox_payload,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(outbox_event)
        self.db.commit()

        logger.info(
            "Successfully ingested order %s (external_id: %s) for tenant %s, outbox event: %s",
            order.id,
            order.external_order_id,
            tenant_id,
            outbox_event_id,
        )

        return OrderIngestResponse(
            order_id=order.id,
            tenant_id=tenant_id,
            external_order_id=order.external_order_id,
            status=order.status,
            currency=order.currency,
            total_amount=order.total_amount,
            items_count=len(payload.items),
            outbox_event_id=outbox_event_id,
            event_type=event_type,
            is_duplicate=False,
            message="Order successfully ingested and queued in transactional outbox.",
        )

    def ingest_batch(
        self,
        tenant_id: uuid.UUID,
        payload: OrderBatchIngestPayload,
    ) -> OrderBatchIngestResponse:
        """Processes a batch of order ingestion payloads within a single store scope."""
        results: List[OrderIngestResponse] = []
        ingested = 0
        duplicates = 0

        for order_payload in payload.orders:
            resp = self.ingest_order(tenant_id=tenant_id, payload=order_payload)
            results.append(resp)
            if resp.is_duplicate:
                duplicates += 1
            else:
                ingested += 1

        return OrderBatchIngestResponse(
            tenant_id=tenant_id,
            total_submitted=len(payload.orders),
            ingested_count=ingested,
            duplicate_count=duplicates,
            orders=results,
        )
