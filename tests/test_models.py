"""CRUD and relationship tests for AGGRIX database models."""

import uuid
from decimal import Decimal
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant


def test_tenant_creation_success(session: Session):
    """Verify successful tenant creation with default UUID and timestamps."""
    tenant = Tenant(
        name="Shopify Test Store",
        domain="shopify-test-store.myshopify.com",
    )
    session.add(tenant)
    session.flush()

    assert tenant.id is not None
    assert isinstance(tenant.id, uuid.UUID)
    assert tenant.name == "Shopify Test Store"
    assert tenant.domain == "shopify-test-store.myshopify.com"


def test_customer_creation_success(session: Session):
    """Verify customer creation linked to a valid tenant."""
    tenant = Tenant(name="Customer Store", domain="customer-store.myshopify.com")
    session.add(tenant)
    session.flush()

    customer = Customer(
        tenant_id=tenant.id,
        email="customer@example.com",
        name="Jane Doe",
    )
    session.add(customer)
    session.flush()

    assert customer.id is not None
    assert customer.tenant_id == tenant.id
    assert customer.email == "customer@example.com"
    assert customer.name == "Jane Doe"
    assert customer.tenant.id == tenant.id


def test_product_creation_success(session: Session):
    """Verify product creation with SKU, price, and currency."""
    tenant = Tenant(name="Product Store", domain="product-store.myshopify.com")
    session.add(tenant)
    session.flush()

    product = Product(
        tenant_id=tenant.id,
        name="Wireless Headphones",
        sku="WH-1000XM5",
        price=Decimal("349.99"),
        currency="USD",
    )
    session.add(product)
    session.flush()

    assert product.id is not None
    assert product.tenant_id == tenant.id
    assert product.sku == "WH-1000XM5"
    assert product.price == Decimal("349.99")
    assert product.currency == "USD"


def test_order_and_order_item_relationship(session: Session):
    """Verify order and order-item lifecycle and bidirectional relationship."""
    tenant = Tenant(name="Order Store", domain="order-store.myshopify.com")
    session.add(tenant)
    session.flush()

    customer = Customer(
        tenant_id=tenant.id,
        email="buyer@example.com",
        name="Alice Buyer",
    )
    product = Product(
        tenant_id=tenant.id,
        name="Espresso Machine",
        sku="ESP-500",
        price=Decimal("599.00"),
        currency="USD",
    )
    session.add_all([customer, product])
    session.flush()

    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        external_order_id="SHPFY-1001",
        total_amount=Decimal("1198.00"),
        currency="USD",
        status="pending",
    )
    session.add(order)
    session.flush()

    order_item = OrderItem(
        tenant_id=tenant.id,
        order_id=order.id,
        product_id=product.id,
        quantity=2,
        unit_price=Decimal("599.00"),
    )
    session.add(order_item)
    session.flush()

    assert len(order.items) == 1
    assert order.items[0].id == order_item.id
    assert order_item.order.id == order.id
    assert order_item.product.id == product.id
    assert order.customer.id == customer.id


def test_outbox_event_creation(session: Session):
    """Verify outbox event creation with JSON payload and pending status."""
    tenant = Tenant(name="Event Store", domain="event-store.myshopify.com")
    session.add(tenant)
    session.flush()

    event = OutboxEvent(
        tenant_id=tenant.id,
        event_type="order.created",
        payload={"order_id": str(uuid.uuid4()), "amount": "150.00", "currency": "USD"},
    )
    session.add(event)
    session.flush()

    assert event.id is not None
    assert event.tenant_id == tenant.id
    assert event.event_type == "order.created"
    assert event.payload["amount"] == "150.00"
    assert event.processed_at is None


def test_product_price_check_constraint(session: Session):
    """Verify database check constraint rejects negative product prices."""
    tenant = Tenant(name="Check Store", domain="check-store.myshopify.com")
    session.add(tenant)
    session.flush()

    bad_product = Product(
        tenant_id=tenant.id,
        name="Invalid Item",
        sku="INV-01",
        price=Decimal("-10.00"),
        currency="USD",
    )
    session.add(bad_product)
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_order_item_quantity_check_constraint(session: Session):
    """Verify database check constraint rejects zero or negative quantity."""
    tenant = Tenant(name="Qty Store", domain="qty-store.myshopify.com")
    session.add(tenant)
    session.flush()

    customer = Customer(tenant_id=tenant.id, email="qty@example.com")
    product = Product(
        tenant_id=tenant.id,
        name="Gadget",
        sku="GDG-01",
        price=Decimal("10.00"),
    )
    session.add_all([customer, product])
    session.flush()

    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        external_order_id="ORD-QTY-1",
        total_amount=Decimal("0.00"),
    )
    session.add(order)
    session.flush()

    bad_item = OrderItem(
        tenant_id=tenant.id,
        order_id=order.id,
        product_id=product.id,
        quantity=0,
        unit_price=Decimal("10.00"),
    )
    session.add(bad_item)
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()
