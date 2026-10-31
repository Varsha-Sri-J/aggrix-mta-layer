"""Automated tests for AGGRIX Incremental Synthetic Data Generation.

Verifies:
1. Incremental configuration bounds and offset validation.
2. Distinct, deterministic tenant domain and store generation across offsets.
3. Customer email, product SKU, and order sequence offset continuity.
4. Outbox events marked unprocessed (processed_at = None) for live worker.
5. Collision detection and duplicate prevention.
6. Incremental dry-run preview accuracy.
7. Appending orders and entities to existing tenants preserving tenant isolation.
8. Streaming insertion with commit_per_tenant memory management.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.generator import (
    SYNTHETIC_DOMAIN_SUFFIX,
    GeneratorConfig,
    SyntheticDataGenerator,
)
from app.generator.cli import main, parse_args
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant


def test_incremental_config_validation():
    """Verify offset bounds, incremental flags, and validation rules."""
    valid = GeneratorConfig(
        tenants_count=3,
        tenant_offset=5,
        customer_offset=100,
        product_offset=50,
        order_offset=1000,
        incremental=True,
        commit_per_tenant=True,
        all_outbox_unprocessed=True,
    )
    valid.validate()
    assert valid.tenant_offset == 5
    assert valid.customer_offset == 100
    assert valid.all_outbox_unprocessed is True

    with pytest.raises(ValueError, match="tenant_offset"):
        GeneratorConfig(tenant_offset=-1).validate()

    with pytest.raises(ValueError, match="order_offset"):
        GeneratorConfig(order_offset=-5).validate()


def test_incremental_tenant_domains_distinct():
    """Verify tenant offsets produce distinct domains that do not collide with initial batches."""
    as_of = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    config_initial = GeneratorConfig(tenants_count=5, tenant_offset=0, seed=42, as_of=as_of)
    config_next = GeneratorConfig(tenants_count=5, tenant_offset=5, seed=42, as_of=as_of)

    ds_initial = SyntheticDataGenerator(config_initial).generate_dataset()
    ds_next = SyntheticDataGenerator(config_next).generate_dataset()

    initial_domains = [t.domain for t in ds_initial.tenants]
    next_domains = [t.domain for t in ds_next.tenants]

    # No domain overlap
    assert set(initial_domains).isdisjoint(set(next_domains))
    assert len(next_domains) == 5
    assert "solstice-home-hearth.synthetic.aggrix.test" in next_domains


def test_customer_product_and_order_offset_sequences():
    """Verify that offset values generate sequential, non-overlapping IDs."""
    as_of = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    config = GeneratorConfig(
        tenants_count=1,
        customers_per_tenant=5,
        products_per_tenant=5,
        orders_per_tenant=5,
        customer_offset=500,
        product_offset=100,
        order_offset=2000,
        seed=123,
        as_of=as_of,
    )
    dataset = SyntheticDataGenerator(config).generate_dataset()

    # Customer email sequence checks
    for cust in dataset.customers:
        num_part = cust.email.split("@")[0].split(".")[-1]
        assert int(num_part) > 500

    # Product SKU sequence checks
    for prod in dataset.products:
        sku_num = int(prod.sku.split("-")[-1])
        assert sku_num > 100

    # Order external ID sequence checks
    for order in dataset.orders:
        order_num = int(order.external_order_id.split("-")[-1])
        assert order_num > 2000


def test_all_outbox_unprocessed_flag():
    """Verify that all_outbox_unprocessed ensures 100% of outbox events are marked pending."""
    config = GeneratorConfig(
        tenants_count=1,
        customers_per_tenant=3,
        products_per_tenant=3,
        orders_per_tenant=10,
        all_outbox_unprocessed=True,
        seed=42,
    )
    dataset = SyntheticDataGenerator(config).generate_dataset()

    assert len(dataset.outbox_events) >= 10
    assert all(e.processed_at is None for e in dataset.outbox_events)
    assert dataset.stats.unprocessed_outbox_count == len(dataset.outbox_events)


def test_duplicate_collision_prevention(session: Session):
    """Verify that duplicate candidate tenant domains trigger prevention error."""
    config_1 = GeneratorConfig(tenants_count=2, tenant_offset=0, orders_per_tenant=2, seed=42)
    gen_1 = SyntheticDataGenerator(config_1)
    gen_1.insert_dataset(session=session)

    # Attempting to insert overlapping tenant domain (offset 0 again)
    config_colliding = GeneratorConfig(tenants_count=1, tenant_offset=0, orders_per_tenant=2, seed=99)
    gen_colliding = SyntheticDataGenerator(config_colliding)

    colliding = gen_colliding.check_duplicate_prevention(session=session)
    assert len(colliding) == 1
    assert "nordic-living-goods.synthetic.aggrix.test" in colliding

    with pytest.raises(ValueError, match="Accidental duplicate generation prevented"):
        gen_colliding.insert_dataset_streaming(session=session, prevent_duplicates=True)

    # Clean up test records
    gen_1.cleanup_synthetic_data(session=session, confirm=True)


def test_incremental_dry_run_preview(session: Session):
    """Verify preview_incremental_generation calculates counts without writing to database."""
    config_init = GeneratorConfig(tenants_count=2, tenant_offset=0, customers_per_tenant=5, products_per_tenant=5, orders_per_tenant=10, seed=42)
    gen_init = SyntheticDataGenerator(config_init)
    gen_init.insert_dataset(session=session)

    config_next = GeneratorConfig(tenants_count=3, tenant_offset=2, customers_per_tenant=5, products_per_tenant=5, orders_per_tenant=10, seed=42)
    gen_next = SyntheticDataGenerator(config_next)

    preview = gen_next.preview_incremental_generation(session=session)
    assert preview.existing_tenants_count == 2
    assert preview.existing_customers_count == 10
    assert preview.existing_orders_count == 20
    assert preview.planned_tenants_count == 3
    assert preview.planned_customers_count == 15
    assert preview.planned_orders_count == 30
    assert len(preview.colliding_domains) == 0

    # Database was unmodified by preview
    assert session.execute(select(func.count()).select_from(Tenant)).scalar() == 2

    # Clean up test records
    gen_init.cleanup_synthetic_data(session=session, confirm=True)


def test_append_incremental_records_to_existing_tenant(session: Session):
    """Verify appending orders, items, and outbox events to an existing tenant."""
    config_init = GeneratorConfig(tenants_count=1, tenant_offset=0, customers_per_tenant=5, products_per_tenant=5, orders_per_tenant=5, seed=42)
    gen_init = SyntheticDataGenerator(config_init)
    gen_init.insert_dataset(session=session)

    tenant = session.execute(select(Tenant)).scalar_one()

    # Append 10 more orders to this exact tenant
    config_append = GeneratorConfig(orders_per_tenant=10, all_outbox_unprocessed=True, seed=99)
    gen_append = SyntheticDataGenerator(config_append)

    stats = gen_append.insert_incremental_for_tenant(session=session, tenant_id=tenant.id)
    assert stats.orders_count == 10
    assert stats.unprocessed_outbox_count == stats.outbox_events_count

    # Total orders for tenant is now 15
    tenant_orders = session.execute(
        select(Order).where(Order.tenant_id == tenant.id).order_by(Order.created_at)
    ).scalars().all()
    assert len(tenant_orders) == 15

    # Check external IDs are distinct (SHP-000001 to SHP-000015)
    external_ids = {o.external_order_id for o in tenant_orders}
    assert len(external_ids) == 15

    # Clean up
    gen_init.cleanup_synthetic_data(session=session, confirm=True)


def test_streaming_commit_per_tenant(session: Session):
    """Verify commit_per_tenant commits and flushes cleanly."""
    config = GeneratorConfig(
        tenants_count=2,
        tenant_offset=10,
        customers_per_tenant=3,
        products_per_tenant=3,
        orders_per_tenant=4,
        commit_per_tenant=True,
        seed=42,
    )
    generator = SyntheticDataGenerator(config)
    stats = generator.insert_dataset_streaming(session=session, commit_per_tenant=True)

    assert stats.tenants_count == 2
    assert stats.orders_count == 8

    # Clean up
    generator.cleanup_synthetic_data(session=session, confirm=True)


def test_cli_incremental_dry_run(capsys):
    """Verify CLI flags --incremental --dry-run invoke the incremental preview."""
    exit_code = main([
        "--dry-run",
        "--incremental",
        "--tenants", "2",
        "--orders-per-tenant", "5",
        "--seed", "42",
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "INCREMENTAL DRY RUN PREVIEW" in captured.out
    assert "Planned New" in captured.out
    assert "Projected Total" in captured.out
