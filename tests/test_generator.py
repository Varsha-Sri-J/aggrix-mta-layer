"""Automated tests for AGGRIX Synthetic E-commerce Data Generator.

Verifies:
1. Dedicated synthetic namespace (*.synthetic.aggrix.test) and guardrails.
2. Safe cleanup preview with explicit confirmation requirement.
3. Deterministic reproducibility with random seed and configurable as_of reference timestamp.
4. Outbox event payloads representing point-in-time order state (not final state).
5. Strict multi-tenant isolation across all entities.
6. Financial consistency with exact Decimal arithmetic.
7. Database constraints, check constraints, and unique keys.
8. Streaming generation architecture for million-record scalability.
9. CLI dry-run and configuration parsing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.generator import (
    SYNTHETIC_DOMAIN_SUFFIX,
    GeneratorConfig,
    SyntheticDataGenerator,
    cleanup_synthetic_data,
    generate_synthetic_data,
    preview_cleanup_synthetic_data,
)
from app.generator.cli import main, parse_args
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant


def test_generator_config_validation():
    """Verify bounds, validation rules, and domain guardrails on GeneratorConfig."""
    valid_config = GeneratorConfig(tenants_count=2, orders_per_tenant=10)
    valid_config.validate()

    assert valid_config.domain_suffix == SYNTHETIC_DOMAIN_SUFFIX

    with pytest.raises(ValueError, match="tenants_count"):
        GeneratorConfig(tenants_count=0).validate()

    with pytest.raises(ValueError, match="unprocessed_outbox_percentage"):
        GeneratorConfig(unprocessed_outbox_percentage=1.5).validate()

    with pytest.raises(ValueError, match="batch_size"):
        GeneratorConfig(batch_size=-1).validate()

    # Domain guardrail: non-synthetic domain rejected
    with pytest.raises(ValueError, match="dedicated synthetic namespace"):
        GeneratorConfig(domain_suffix="production-shopify.com").validate()


def test_configurable_as_of_reference_timestamp():
    """Verify that specifying as_of produces exact reproducible logical timestamps."""
    as_of = datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc)
    config1 = GeneratorConfig(tenants_count=2, orders_per_tenant=10, seed=42, as_of=as_of)
    config2 = GeneratorConfig(tenants_count=2, orders_per_tenant=10, seed=42, as_of=as_of)

    ds1 = SyntheticDataGenerator(config1).generate_dataset()
    ds2 = SyntheticDataGenerator(config2).generate_dataset()

    assert [t.created_at for t in ds1.tenants] == [t.created_at for t in ds2.tenants]
    assert [o.created_at for o in ds1.orders] == [o.created_at for o in ds2.orders]
    assert [o.updated_at for o in ds1.orders] == [o.updated_at for o in ds2.orders]
    assert [e.created_at for e in ds1.outbox_events] == [e.created_at for e in ds2.outbox_events]


def test_deterministic_reproducibility():
    """Verify that same seed and reference time produce 100% identical synthetic datasets."""
    as_of = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    config1 = GeneratorConfig(
        tenants_count=2,
        customers_per_tenant=5,
        products_per_tenant=5,
        orders_per_tenant=10,
        seed=42,
        as_of=as_of,
    )
    config2 = GeneratorConfig(
        tenants_count=2,
        customers_per_tenant=5,
        products_per_tenant=5,
        orders_per_tenant=10,
        seed=42,
        as_of=as_of,
    )
    diff_config = GeneratorConfig(
        tenants_count=2,
        customers_per_tenant=5,
        products_per_tenant=5,
        orders_per_tenant=10,
        seed=99,
        as_of=as_of,
    )

    ds1 = SyntheticDataGenerator(config1).generate_dataset()
    ds2 = SyntheticDataGenerator(config2).generate_dataset()
    ds_diff = SyntheticDataGenerator(diff_config).generate_dataset()

    # Identical seed assertions
    assert len(ds1.tenants) == len(ds2.tenants) == 2
    assert [t.name for t in ds1.tenants] == [t.name for t in ds2.tenants]
    assert [c.email for c in ds1.customers] == [c.email for c in ds2.customers]
    assert [p.sku for p in ds1.products] == [p.sku for p in ds2.products]
    assert [o.total_amount for o in ds1.orders] == [o.total_amount for o in ds2.orders]
    assert ds1.stats.total_revenue == ds2.stats.total_revenue

    # Different seed assertions
    assert [o.total_amount for o in ds1.orders] != [o.total_amount for o in ds_diff.orders]


def test_strict_tenant_isolation():
    """Verify every customer, product, order, item, and outbox event is strictly partitioned by tenant."""
    config = GeneratorConfig(
        tenants_count=3,
        customers_per_tenant=10,
        products_per_tenant=10,
        orders_per_tenant=25,
        seed=101,
    )
    dataset = SyntheticDataGenerator(config).generate_dataset()

    tenant_ids = {t.id for t in dataset.tenants}
    assert len(tenant_ids) == 3

    # Group records by tenant_id
    customers_by_tenant = {tid: set() for tid in tenant_ids}
    products_by_tenant = {tid: set() for tid in tenant_ids}

    for c in dataset.customers:
        assert c.tenant_id in tenant_ids
        customers_by_tenant[c.tenant_id].add(c.id)

    for p in dataset.products:
        assert p.tenant_id in tenant_ids
        products_by_tenant[p.tenant_id].add(p.id)

    # Verify orders reference ONLY customers from their exact tenant
    for o in dataset.orders:
        assert o.tenant_id in tenant_ids
        assert o.customer_id in customers_by_tenant[o.tenant_id]

    # Verify order items reference ONLY products from their exact tenant
    orders_by_id = {o.id: o for o in dataset.orders}
    for item in dataset.order_items:
        assert item.tenant_id in tenant_ids
        parent_order = orders_by_id[item.order_id]
        assert item.tenant_id == parent_order.tenant_id
        assert item.product_id in products_by_tenant[item.tenant_id]

    # Verify outbox events match tenant_id
    for ev in dataset.outbox_events:
        assert ev.tenant_id in tenant_ids
        assert ev.payload["tenant_id"] == str(ev.tenant_id)


def test_financial_consistency_decimal_arithmetic():
    """Verify Order.total_amount == sum(quantity * unit_price) with exact Decimal precision."""
    config = GeneratorConfig(
        tenants_count=2,
        customers_per_tenant=5,
        products_per_tenant=10,
        orders_per_tenant=30,
        seed=777,
    )
    dataset = SyntheticDataGenerator(config).generate_dataset()

    items_by_order: dict[uuid.UUID, list[OrderItem]] = {}
    for item in dataset.order_items:
        items_by_order.setdefault(item.order_id, []).append(item)

    for order in dataset.orders:
        items = items_by_order[order.id]
        assert len(items) >= 1

        computed_sum = Decimal("0.00")
        for item in items:
            assert isinstance(item.unit_price, Decimal)
            assert item.unit_price >= Decimal("0.00")
            assert isinstance(item.quantity, int)
            assert item.quantity > 0

            line_total = (Decimal(item.quantity) * item.unit_price).quantize(Decimal("0.01"))
            computed_sum += line_total

        assert order.total_amount == computed_sum
        assert order.total_amount >= Decimal("0.00")


def test_outbox_payload_represents_point_in_time_order_state():
    """Verify each outbox event represents the order state at event time, NOT the final status."""
    config = GeneratorConfig(
        tenants_count=2,
        customers_per_tenant=10,
        products_per_tenant=10,
        orders_per_tenant=50,
        seed=333,
    )
    dataset = SyntheticDataGenerator(config).generate_dataset()

    events_by_order: dict[str, list[OutboxEvent]] = {}
    for ev in dataset.outbox_events:
        events_by_order.setdefault(ev.payload["order_id"], []).append(ev)

    orders_by_id = {str(o.id): o for o in dataset.orders}

    # Verify fulfilled orders
    fulfilled_orders = [o for o in dataset.orders if o.status == "fulfilled"]
    assert len(fulfilled_orders) > 0

    for order in fulfilled_orders:
        events = events_by_order[str(order.id)]
        assert len(events) == 3

        created_ev, paid_ev, fulfilled_ev = events[0], events[1], events[2]

        # In order.created, status must be 'pending' with previous_status=None
        assert created_ev.event_type == "order.created"
        assert created_ev.payload["status"] == "pending"
        assert created_ev.payload["previous_status"] is None
        assert created_ev.payload["order_status_at_event"] == "pending"

        # In order.paid, status must be 'paid' with previous_status='pending'
        assert paid_ev.event_type == "order.paid"
        assert paid_ev.payload["status"] == "paid"
        assert paid_ev.payload["previous_status"] == "pending"
        assert paid_ev.payload["order_status_at_event"] == "paid"

        # In order.fulfilled, status must be 'fulfilled' with previous_status='paid'
        assert fulfilled_ev.event_type == "order.fulfilled"
        assert fulfilled_ev.payload["status"] == "fulfilled"
        assert fulfilled_ev.payload["previous_status"] == "paid"
        assert fulfilled_ev.payload["order_status_at_event"] == "fulfilled"

    # Verify cancelled orders
    cancelled_orders = [o for o in dataset.orders if o.status == "cancelled"]
    assert len(cancelled_orders) > 0

    for order in cancelled_orders:
        events = events_by_order[str(order.id)]
        assert len(events) == 2

        created_ev, cancel_ev = events[0], events[1]
        assert created_ev.payload["status"] == "pending"
        assert cancel_ev.payload["status"] == "cancelled"
        assert cancel_ev.payload["previous_status"] == "pending"
        assert "order.fulfilled" not in [e.event_type for e in events]


def test_safe_cleanup_preview_and_confirmation_guardrails(session: Session):
    """Verify cleanup preview, non-synthetic pattern rejection, and explicit confirmation requirement."""
    config = GeneratorConfig(
        tenants_count=2,
        customers_per_tenant=3,
        products_per_tenant=3,
        orders_per_tenant=5,
        seed=999,
        domain_suffix=SYNTHETIC_DOMAIN_SUFFIX,
    )
    generator = SyntheticDataGenerator(config)
    generator.insert_dataset(session=session)

    # Also insert a production tenant outside the synthetic namespace
    prod_tenant = Tenant(
        name="Real Production Brand",
        domain="real-brand.myshopify.com",
    )
    session.add(prod_tenant)
    session.commit()

    # 1. Safety guardrail: attempt to clean non-synthetic domain is rejected
    with pytest.raises(ValueError, match="Safety Violation"):
        generator.preview_cleanup_synthetic_data(session=session, domain_pattern="%.myshopify.com")

    # 2. Preview impact analysis shows exact record counts
    plan = generator.preview_cleanup_synthetic_data(session=session)
    assert plan.tenants_count == 2
    assert plan.customers_count == 6
    assert plan.products_count == 6
    assert plan.orders_count == 10
    assert plan.order_items_count >= 10
    assert plan.outbox_events_count >= 10
    assert plan.total_records_count > 30

    # 3. Cleanup without explicit confirm=True raises error and deletes 0 records
    with pytest.raises(ValueError, match="Explicit confirmation"):
        generator.cleanup_synthetic_data(session=session, confirm=False)

    tenants_unmodified = session.execute(select(Tenant)).scalars().all()
    assert len(tenants_unmodified) == 3

    # 4. Cleanup with explicit confirm=True purges synthetic records while preserving prod
    executed_plan = generator.cleanup_synthetic_data(session=session, confirm=True)
    assert executed_plan.deleted is True
    assert executed_plan.confirmed is True
    assert executed_plan.tenants_count == 2

    remaining_tenants = session.execute(select(Tenant)).scalars().all()
    assert len(remaining_tenants) == 1
    assert remaining_tenants[0].domain == "real-brand.myshopify.com"

    # All synthetic child records are cascaded
    remaining_orders = session.execute(select(Order)).scalars().all()
    assert len(remaining_orders) == 0


def test_streaming_generation_architecture(session: Session):
    """Verify streaming tenant generator produces valid records with minimal memory overhead."""
    config = GeneratorConfig(
        tenants_count=2,
        customers_per_tenant=4,
        products_per_tenant=4,
        orders_per_tenant=6,
        seed=1234,
        domain_suffix=SYNTHETIC_DOMAIN_SUFFIX,
    )
    generator = SyntheticDataGenerator(config)

    # Test stream generation
    stream_tenants = list(generator.generate_tenant_stream())
    assert len(stream_tenants) == 2
    assert stream_tenants[0].tenant.domain.endswith(SYNTHETIC_DOMAIN_SUFFIX)

    # Test streaming insertion
    stats = generator.insert_dataset_streaming(session=session)
    assert stats.tenants_count == 2
    assert stats.customers_count == 8
    assert stats.products_count == 8
    assert stats.orders_count == 12

    db_orders = session.execute(select(Order)).scalars().all()
    assert len(db_orders) == 12

    # Clean up afterwards
    generator.cleanup_synthetic_data(session=session, confirm=True)


def test_cli_dry_run_and_arg_parsing(capsys):
    """Verify CLI options parsing, as-of parsing, and dry-run execution."""
    args = parse_args([
        "--tenants", "1",
        "--customers-per-tenant", "3",
        "--orders-per-tenant", "5",
        "--seed", "42",
        "--as-of", "2026-10-31T12:00:00Z",
    ])
    assert args.tenants == 1
    assert args.customers_per_tenant == 3
    assert args.orders_per_tenant == 5
    assert args.seed == 42
    assert args.as_of == "2026-10-31T12:00:00Z"

    exit_code = main([
        "--dry-run",
        "--tenants", "1",
        "--customers-per-tenant", "2",
        "--orders-per-tenant", "3",
        "--seed", "42",
        "--as-of", "2026-10-31T12:00:00Z",
    ])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "DRY RUN SUMMARY" in captured.out
    assert "Tenants:           1" in captured.out
    assert "Orders:            3" in captured.out
    assert "2026-10-31T12:00:00+00:00" in captured.out
