"""Multi-tenant isolation and tenant-aware constraint tests."""

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


def test_cross_tenant_order_customer_rejection(session: Session):
    """Verify that an order CANNOT reference a customer from a different tenant."""
    tenant_a = Tenant(name="Store A", domain="store-a.myshopify.com")
    tenant_b = Tenant(name="Store B", domain="store-b.myshopify.com")
    session.add_all([tenant_a, tenant_b])
    session.flush()

    # Customer belongs to Tenant A
    customer_a = Customer(tenant_id=tenant_a.id, email="shared@example.com", name="User A")
    session.add(customer_a)
    session.flush()

    # Tenant B attempts to create an order referencing Customer A
    cross_tenant_order = Order(
        tenant_id=tenant_b.id,  # Belongs to B
        customer_id=customer_a.id,  # Belongs to A!
        external_order_id="ORD-X-1",
        total_amount=Decimal("50.00"),
    )
    session.add(cross_tenant_order)

    # Must be physically rejected by composite foreign key fk_orders_customer_tenant
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_cross_tenant_order_item_order_rejection(session: Session):
    """Verify an order item CANNOT reference an order from a different tenant."""
    tenant_a = Tenant(name="Store A", domain="item-a.myshopify.com")
    tenant_b = Tenant(name="Store B", domain="item-b.myshopify.com")
    session.add_all([tenant_a, tenant_b])
    session.flush()

    customer_a = Customer(tenant_id=tenant_a.id, email="cust-a@example.com")
    session.add(customer_a)
    session.flush()

    order_a = Order(
        tenant_id=tenant_a.id,
        customer_id=customer_a.id,
        external_order_id="ORD-A-1",
        total_amount=Decimal("100.00"),
    )
    product_b = Product(
        tenant_id=tenant_b.id,
        name="Product B",
        sku="SKU-B",
        price=Decimal("100.00"),
    )
    session.add_all([order_a, product_b])
    session.flush()

    # Tenant B tries to attach an item to Tenant A's order
    bad_item = OrderItem(
        tenant_id=tenant_b.id,
        order_id=order_a.id,  # Belongs to Tenant A!
        product_id=product_b.id,
        quantity=1,
        unit_price=Decimal("100.00"),
    )
    session.add(bad_item)

    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_cross_tenant_order_item_product_rejection(session: Session):
    """Verify an order item CANNOT reference a product from a different tenant."""
    tenant_a = Tenant(name="Store A", domain="prod-a.myshopify.com")
    tenant_b = Tenant(name="Store B", domain="prod-b.myshopify.com")
    session.add_all([tenant_a, tenant_b])
    session.flush()

    customer_a = Customer(tenant_id=tenant_a.id, email="cust-a2@example.com")
    session.add(customer_a)
    session.flush()

    order_a = Order(
        tenant_id=tenant_a.id,
        customer_id=customer_a.id,
        external_order_id="ORD-A-2",
        total_amount=Decimal("75.00"),
    )
    # Product belongs to Tenant B
    product_b = Product(
        tenant_id=tenant_b.id,
        name="Tenant B Product",
        sku="SKU-B2",
        price=Decimal("75.00"),
    )
    session.add_all([order_a, product_b])
    session.flush()

    # Order item belongs to Tenant A, but references Tenant B's product
    bad_item = OrderItem(
        tenant_id=tenant_a.id,
        order_id=order_a.id,
        product_id=product_b.id,  # Belongs to Tenant B!
        quantity=1,
        unit_price=Decimal("75.00"),
    )
    session.add(bad_item)

    # Must be rejected by composite foreign key fk_order_items_product_tenant
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_tenant_aware_customer_email_uniqueness(session: Session):
    """Verify customer emails can collide across tenants, but are unique within a tenant."""
    tenant_1 = Tenant(name="Store 1", domain="store1.myshopify.com")
    tenant_2 = Tenant(name="Store 2", domain="store2.myshopify.com")
    session.add_all([tenant_1, tenant_2])
    session.flush()

    # Same email in Store 1
    c1 = Customer(tenant_id=tenant_1.id, email="vip@example.com", name="VIP 1")
    session.add(c1)
    session.flush()

    # Same email in Store 2: MUST SUCCEED
    c2 = Customer(tenant_id=tenant_2.id, email="vip@example.com", name="VIP 2")
    session.add(c2)
    session.flush()
    assert c1.id != c2.id

    # Duplicate email in Store 1: MUST FAIL
    c_dup = Customer(tenant_id=tenant_1.id, email="vip@example.com", name="VIP Dup")
    session.add(c_dup)
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_tenant_aware_product_sku_uniqueness(session: Session):
    """Verify product SKUs can collide across tenants, but are unique within a tenant."""
    tenant_1 = Tenant(name="Brand 1", domain="brand1.myshopify.com")
    tenant_2 = Tenant(name="Brand 2", domain="brand2.myshopify.com")
    session.add_all([tenant_1, tenant_2])
    session.flush()

    # Same SKU in Brand 1
    p1 = Product(tenant_id=tenant_1.id, name="Shirt", sku="SHIRT-BLK-M", price=Decimal("25.00"))
    session.add(p1)
    session.flush()

    # Same SKU in Brand 2: MUST SUCCEED
    p2 = Product(tenant_id=tenant_2.id, name="Shirt", sku="SHIRT-BLK-M", price=Decimal("29.00"))
    session.add(p2)
    session.flush()

    # Duplicate SKU in Brand 1: MUST FAIL
    p_dup = Product(tenant_id=tenant_1.id, name="Shirt 2", sku="SHIRT-BLK-M", price=Decimal("20.00"))
    session.add(p_dup)
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_tenant_aware_external_order_id_uniqueness(session: Session):
    """Verify external order IDs (e.g. #1001) are unique per tenant but can exist across tenants."""
    tenant_1 = Tenant(name="Store 1", domain="ord1.myshopify.com")
    tenant_2 = Tenant(name="Store 2", domain="ord2.myshopify.com")
    session.add_all([tenant_1, tenant_2])
    session.flush()

    c1 = Customer(tenant_id=tenant_1.id, email="c1@example.com")
    c2 = Customer(tenant_id=tenant_2.id, email="c2@example.com")
    session.add_all([c1, c2])
    session.flush()

    # Order #1001 in Store 1
    o1 = Order(tenant_id=tenant_1.id, customer_id=c1.id, external_order_id="#1001", total_amount=Decimal("10.00"))
    session.add(o1)
    session.flush()

    # Order #1001 in Store 2: MUST SUCCEED
    o2 = Order(tenant_id=tenant_2.id, customer_id=c2.id, external_order_id="#1001", total_amount=Decimal("20.00"))
    session.add(o2)
    session.flush()

    # Duplicate Order #1001 in Store 1: MUST FAIL
    o_dup = Order(tenant_id=tenant_1.id, customer_id=c1.id, external_order_id="#1001", total_amount=Decimal("30.00"))
    session.add(o_dup)
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_tenant_cascade_delete(session: Session):
    """Verify that deleting a tenant cascades and removes all dependent tenant records."""
    tenant = Tenant(name="Cascade Store", domain="cascade.myshopify.com")
    session.add(tenant)
    session.flush()

    customer = Customer(tenant_id=tenant.id, email="cascade@example.com")
    product = Product(tenant_id=tenant.id, name="Item", sku="CAS-01", price=Decimal("15.00"))
    session.add_all([customer, product])
    session.flush()

    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        external_order_id="CAS-ORD-1",
        total_amount=Decimal("15.00"),
    )
    session.add(order)
    session.flush()

    item = OrderItem(
        tenant_id=tenant.id,
        order_id=order.id,
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("15.00"),
    )
    event = OutboxEvent(
        tenant_id=tenant.id,
        event_type="tenant.created",
        payload={"tenant_id": str(tenant.id)},
    )
    session.add_all([item, event])
    session.flush()

    # Save IDs prior to deletion
    customer_id = customer.id
    product_id = product.id
    order_id = order.id
    item_id = item.id
    event_id = event.id

    # Delete the tenant
    session.delete(tenant)
    session.flush()
    session.expunge_all()

    # All related records must be cascade deleted
    assert session.get(Customer, customer_id) is None
    assert session.get(Product, product_id) is None
    assert session.get(Order, order_id) is None
    assert session.get(OrderItem, item_id) is None
    assert session.get(OutboxEvent, event_id) is None
