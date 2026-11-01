"""Entity builders for AGGRIX Synthetic E-commerce Data Generator.

Constructs valid, constraint-compliant SQLAlchemy model instances with
strict multi-tenant isolation, financial consistency, and causal timestamps.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from app.generator.config import GeneratorConfig
from app.generator.providers import (
    EMAIL_DOMAINS,
    FIRST_NAMES,
    LAST_NAMES,
    PRODUCT_TEMPLATES,
    STORE_NAMES,
    slugify,
)
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant


def build_tenant(
    rng: random.Random,
    index: int,
    base_time: datetime,
    config: GeneratorConfig,
) -> Tenant:
    """Build a deterministic Tenant model."""
    name_template = STORE_NAMES[index % len(STORE_NAMES)]
    suffix = f" {index + 1}" if index >= len(STORE_NAMES) else ""
    store_name = f"{name_template}{suffix}"
    slug = slugify(store_name)
    domain = f"{slug}.{config.domain_suffix}"

    tenant_created = base_time - timedelta(days=config.days_history + 10)
    tenant_id = uuid.uuid4()

    return Tenant(
        id=tenant_id,
        name=store_name,
        domain=domain,
        created_at=tenant_created,
        updated_at=tenant_created,
    )


def build_customers(
    rng: random.Random,
    tenant_id: uuid.UUID,
    count: int,
    base_time: datetime,
    config: GeneratorConfig,
    customer_offset: int = 0,
) -> List[Customer]:
    """Build deterministic, tenant-isolated Customer models with unique emails."""
    customers: List[Customer] = []
    tenant_created = base_time - timedelta(days=config.days_history + 10)
    max_customer_days = max(1, config.days_history - 5)
    offset = customer_offset or config.customer_offset

    for i in range(count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        email_domain = rng.choice(EMAIL_DOMAINS)
        seq = offset + i + 1
        email = f"{first.lower()}.{last.lower()}.{seq:04d}@{email_domain}"

        # Distributed registration between tenant onboarding and 5 days ago
        registration_offset = rng.uniform(0, max_customer_days)
        created_at = tenant_created + timedelta(days=registration_offset)

        customer = Customer(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=email,
            name=f"{first} {last}",
            created_at=created_at,
            updated_at=created_at,
        )
        customers.append(customer)

    return customers


def build_products(
    rng: random.Random,
    tenant_id: uuid.UUID,
    count: int,
    base_time: datetime,
    config: GeneratorConfig,
    product_offset: int = 0,
) -> List[Product]:
    """Build deterministic, tenant-isolated Product catalog items with unique SKUs."""
    products: List[Product] = []
    tenant_created = base_time - timedelta(days=config.days_history + 10)
    offset = product_offset or config.product_offset

    for i in range(count):
        abs_idx = offset + i
        template_idx = abs_idx % len(PRODUCT_TEMPLATES)
        cat_code, base_name, base_price = PRODUCT_TEMPLATES[template_idx]
        multiplier = (abs_idx // len(PRODUCT_TEMPLATES)) + 1
        name = f"{base_name} V{multiplier}" if multiplier > 1 else base_name

        # Ensure unique SKU per tenant
        sku = f"{cat_code}-{abs_idx + 1:04d}"

        # Price variance: +/- 10% around base price, rounded to 2 decimal places
        variation = Decimal(str(rng.randint(-500, 500) / 100.0))
        price = (base_price + variation).quantize(Decimal("0.01"))
        if price <= Decimal("0.00"):
            price = Decimal("9.99")

        created_at = tenant_created + timedelta(hours=rng.randint(1, 48))

        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            sku=sku,
            price=price,
            currency=config.currency,
            created_at=created_at,
            updated_at=created_at,
        )
        products.append(product)

    return products


def build_order_and_items(
    rng: random.Random,
    tenant_id: uuid.UUID,
    customer: Customer,
    products: List[Product],
    order_seq: int,
    base_time: datetime,
    config: GeneratorConfig,
) -> Tuple[Order, List[OrderItem], List[OutboxEvent]]:
    """Build a consistent Order, its line items, and lifecycle OutboxEvents.

    Guarantees:
    1. Tenant isolation across Order, OrderItems, Customer, and Products.
    2. Exact Decimal arithmetic: Order.total_amount == sum(item.quantity * item.unit_price).
    3. Causal lifecycle timestamps and non-contradictory transitions.
    4. Structured JSONB outbox events with configurable pending/unprocessed ratio.
    """
    order_id = uuid.uuid4()
    external_order_id = f"SHP-{order_seq:06d}"

    # Order placement timestamp between customer registration (or 60d ago) and base_time
    history_start = base_time - timedelta(days=config.days_history)
    cust_created = customer.created_at
    if cust_created.tzinfo is None:
        cust_created = cust_created.replace(tzinfo=timezone.utc)
    earliest_time = max(cust_created, history_start)
    if earliest_time >= base_time:
        earliest_time = base_time - timedelta(hours=1)

    window_seconds = max(60, int((base_time - earliest_time).total_seconds()))
    order_created = earliest_time + timedelta(seconds=rng.randint(0, window_seconds))

    # Pick basket size and products (1 to max_items_per_order)
    item_count = rng.randint(config.min_items_per_order, min(config.max_items_per_order, len(products)))
    selected_products = rng.sample(products, item_count)

    items: List[OrderItem] = []
    total_amount = Decimal("0.00")

    for prod in selected_products:
        quantity = rng.randint(config.min_item_quantity, config.max_item_quantity)
        unit_price = prod.price  # Non-negative Decimal

        item_total = (Decimal(quantity) * unit_price).quantize(Decimal("0.01"))
        total_amount += item_total

        item = OrderItem(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            order_id=order_id,
            product_id=prod.id,
            quantity=quantity,
            unit_price=unit_price,
            created_at=order_created,
        )
        items.append(item)

    # Lifecycle state selection
    status_choices = list(config.status_weights.keys())
    status_probs = list(config.status_weights.values())
    status = rng.choices(status_choices, weights=status_probs, k=1)[0]

    # Causal lifecycle progression and outbox events
    outbox_events: List[OutboxEvent] = []
    order_updated = order_created

    # Event 1: order.created (Order state at creation time is always 'pending')
    outbox_events.append(
        _create_outbox_event(
            rng=rng,
            tenant_id=tenant_id,
            order_id=order_id,
            customer_id=customer.id,
            external_order_id=external_order_id,
            event_type="order.created",
            status="pending",
            previous_status=None,
            total_amount=total_amount,
            currency=config.currency,
            items_count=len(items),
            event_time=order_created,
            base_time=base_time,
            unprocessed_percentage=config.unprocessed_outbox_percentage,
            all_unprocessed=config.all_outbox_unprocessed,
        )
    )

    if status in ("paid", "fulfilled"):
        # Payment captured within 5 to 60 minutes after order placement
        pay_offset_seconds = rng.randint(300, 3600)
        paid_time = min(order_created + timedelta(seconds=pay_offset_seconds), base_time)
        order_updated = paid_time

        # Event 2: order.paid (Order state at payment time is 'paid', transitioned from 'pending')
        outbox_events.append(
            _create_outbox_event(
                rng=rng,
                tenant_id=tenant_id,
                order_id=order_id,
                customer_id=customer.id,
                external_order_id=external_order_id,
                event_type="order.paid",
                status="paid",
                previous_status="pending",
                total_amount=total_amount,
                currency=config.currency,
                items_count=len(items),
                event_time=paid_time,
                base_time=base_time,
                unprocessed_percentage=config.unprocessed_outbox_percentage,
                all_unprocessed=config.all_outbox_unprocessed,
            )
        )

        if status == "fulfilled":
            # Fulfillment occurs 6 to 72 hours after payment
            fulfill_offset_hours = rng.randint(6, 72)
            fulfill_time = min(paid_time + timedelta(hours=fulfill_offset_hours), base_time)
            order_updated = fulfill_time

            # Event 3: order.fulfilled (Order state at fulfillment time is 'fulfilled', transitioned from 'paid')
            outbox_events.append(
                _create_outbox_event(
                    rng=rng,
                    tenant_id=tenant_id,
                    order_id=order_id,
                    customer_id=customer.id,
                    external_order_id=external_order_id,
                    event_type="order.fulfilled",
                    status="fulfilled",
                    previous_status="paid",
                    total_amount=total_amount,
                    currency=config.currency,
                    items_count=len(items),
                    event_time=fulfill_time,
                    base_time=base_time,
                    unprocessed_percentage=config.unprocessed_outbox_percentage,
                    all_unprocessed=config.all_outbox_unprocessed,
                )
            )

    elif status == "cancelled":
        # Cancellation occurs 10 minutes to 24 hours after placement
        cancel_offset_minutes = rng.randint(10, 1440)
        cancel_time = min(order_created + timedelta(minutes=cancel_offset_minutes), base_time)
        order_updated = cancel_time

        # Event: order.cancelled (Order state at cancellation time is 'cancelled', transitioned from 'pending')
        outbox_events.append(
            _create_outbox_event(
                rng=rng,
                tenant_id=tenant_id,
                order_id=order_id,
                customer_id=customer.id,
                external_order_id=external_order_id,
                event_type="order.cancelled",
                status="cancelled",
                previous_status="pending",
                total_amount=total_amount,
                currency=config.currency,
                items_count=len(items),
                event_time=cancel_time,
                base_time=base_time,
                unprocessed_percentage=config.unprocessed_outbox_percentage,
                all_unprocessed=config.all_outbox_unprocessed,
            )
        )

    order = Order(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer.id,
        external_order_id=external_order_id,
        total_amount=total_amount,
        currency=config.currency,
        status=status,
        created_at=order_created,
        updated_at=order_updated,
    )

    return order, items, outbox_events


def _create_outbox_event(
    rng: random.Random,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    customer_id: uuid.UUID,
    external_order_id: str,
    event_type: str,
    status: str,
    previous_status: Optional[str],
    total_amount: Decimal,
    currency: str,
    items_count: int,
    event_time: datetime,
    base_time: datetime,
    unprocessed_percentage: float,
    all_unprocessed: bool = False,
) -> OutboxEvent:
    """Build a structured transactional OutboxEvent representing point-in-time order state."""
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "tenant_id": str(tenant_id),
        "order_id": str(order_id),
        "customer_id": str(customer_id),
        "external_order_id": external_order_id,
        "status": status,
        "previous_status": previous_status,
        "order_status_at_event": status,
        "total_amount": str(total_amount),
        "currency": currency,
        "items_count": items_count,
        "occurred_at": event_time.isoformat(),
    }

    # Decide whether this event is processed or pending
    is_unprocessed = all_unprocessed or (rng.random() < unprocessed_percentage)
    processed_at: Optional[datetime] = None

    if not is_unprocessed:
        # Processed between 1 and 30 seconds after event occurred
        proc_time = event_time + timedelta(seconds=rng.randint(1, 30))
        processed_at = min(proc_time, base_time)

    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
        created_at=event_time,
        processed_at=processed_at,
    )
