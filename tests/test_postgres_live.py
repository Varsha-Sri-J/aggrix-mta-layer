"""Live PostgreSQL integration tests (skipped if PostgreSQL instance is offline)."""

import uuid
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant


def test_postgres_live_roundtrip(postgres_session: Session):
    """Verify live PostgreSQL persistence of all multi-tenant entities."""
    # 1. Tenant
    tenant = Tenant(
        name="Postgres Live Store",
        domain=f"pg-live-{uuid.uuid4().hex[:8]}.myshopify.com",
    )
    postgres_session.add(tenant)
    postgres_session.flush()

    # 2. Customer
    customer = Customer(
        tenant_id=tenant.id,
        email="pg-live-user@example.com",
        name="Postgres User",
    )
    postgres_session.add(customer)
    postgres_session.flush()

    # 3. Product
    product = Product(
        tenant_id=tenant.id,
        name="PG Storefront Item",
        sku="SKU-PGLIVE",
        price=Decimal("120.00"),
        currency="USD",
    )
    postgres_session.add(product)
    postgres_session.flush()

    # 4. Order
    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        external_order_id="#PG-1001",
        total_amount=Decimal("240.00"),
        currency="USD",
        status="paid",
    )
    postgres_session.add(order)
    postgres_session.flush()

    # 5. OrderItem
    item = OrderItem(
        tenant_id=tenant.id,
        order_id=order.id,
        product_id=product.id,
        quantity=2,
        unit_price=Decimal("120.00"),
    )
    postgres_session.add(item)
    postgres_session.flush()

    # 6. OutboxEvent with native JSONB
    event = OutboxEvent(
        tenant_id=tenant.id,
        event_type="order.placed",
        payload={"order_id": str(order.id), "total": "240.00"},
    )
    postgres_session.add(event)
    postgres_session.flush()

    assert tenant.id is not None
    assert customer.id is not None
    assert product.id is not None
    assert order.id is not None
    assert item.id is not None
    assert event.id is not None

