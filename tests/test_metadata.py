"""Schema metadata and architectural constraint unit tests."""

import sqlalchemy as sa
from sqlalchemy import Uuid

from app.database.base import Base


def test_required_tables_present_in_metadata():
    """Verify all 6 core tables are registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {
        "tenants",
        "customers",
        "products",
        "orders",
        "order_items",
        "outbox_events",
    }
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"


def test_primary_keys_are_uuid():
    """Verify primary keys across all entities use UUID types."""
    for table_name in ["tenants", "customers", "products", "orders", "order_items", "outbox_events"]:
        table = Base.metadata.tables[table_name]
        pk_cols = list(table.primary_key.columns)
        assert len(pk_cols) == 1, f"Expected single-column primary key on {table_name}"
        assert pk_cols[0].name == "id", f"Expected primary key 'id' on {table_name}"
        assert isinstance(pk_cols[0].type, Uuid), f"Expected UUID primary key on {table_name}"


def test_tenant_id_present_on_all_child_tables():
    """Verify every tenant-owned table contains a non-nullable tenant_id column."""
    tenant_tables = ["customers", "products", "orders", "order_items", "outbox_events"]
    for table_name in tenant_tables:
        table = Base.metadata.tables[table_name]
        assert "tenant_id" in table.c, f"Missing tenant_id in {table_name}"
        tenant_col = table.c["tenant_id"]
        assert not tenant_col.nullable, f"tenant_id in {table_name} must be NOT NULL"
        assert isinstance(tenant_col.type, Uuid), f"tenant_id in {table_name} must be UUID"


def test_composite_foreign_keys_configured():
    """Verify database-level composite foreign key constraints guarantee tenant isolation."""
    orders_table = Base.metadata.tables["orders"]
    order_items_table = Base.metadata.tables["order_items"]

    # 1. Orders -> Customers composite FK: (tenant_id, customer_id) -> (customers.tenant_id, customers.id)
    orders_fks = [
        fk for fk in orders_table.foreign_key_constraints
        if {col.name for col in fk.columns} == {"tenant_id", "customer_id"}
    ]
    assert len(orders_fks) == 1, "Orders must have composite FK (tenant_id, customer_id)"
    fk = orders_fks[0]
    ref_table = fk.referred_table.name
    ref_cols = {elem.column.name for elem in fk.elements}
    assert ref_table == "customers"
    assert ref_cols == {"tenant_id", "id"}
    assert fk.ondelete.upper() == "RESTRICT"

    # 2. OrderItems -> Orders composite FK: (tenant_id, order_id) -> (orders.tenant_id, orders.id)
    order_fks = [
        fk for fk in order_items_table.foreign_key_constraints
        if {col.name for col in fk.columns} == {"tenant_id", "order_id"}
    ]
    assert len(order_fks) == 1, "OrderItems must have composite FK (tenant_id, order_id)"
    assert order_fks[0].referred_table.name == "orders"
    assert {elem.column.name for elem in order_fks[0].elements} == {"tenant_id", "id"}
    assert order_fks[0].ondelete.upper() == "CASCADE"

    # 3. OrderItems -> Products composite FK: (tenant_id, product_id) -> (products.tenant_id, products.id)
    product_fks = [
        fk for fk in order_items_table.foreign_key_constraints
        if {col.name for col in fk.columns} == {"tenant_id", "product_id"}
    ]
    assert len(product_fks) == 1, "OrderItems must have composite FK (tenant_id, product_id)"
    assert product_fks[0].referred_table.name == "products"
    assert {elem.column.name for elem in product_fks[0].elements} == {"tenant_id", "id"}
    assert product_fks[0].ondelete.upper() == "RESTRICT"


def test_composite_unique_constraints_configured():
    """Verify tenant-aware unique constraints exist on all required models."""
    customers_table = Base.metadata.tables["customers"]
    products_table = Base.metadata.tables["products"]
    orders_table = Base.metadata.tables["orders"]
    tenants_table = Base.metadata.tables["tenants"]

    # Tenants domain uniqueness
    tenant_uq_cols = [
        {col.name for col in uq.columns}
        for uq in tenants_table.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert {"domain"} in tenant_uq_cols

    # Customers (tenant_id, email) and (tenant_id, id)
    customer_uq_cols = [
        {col.name for col in uq.columns}
        for uq in customers_table.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert {"tenant_id", "email"} in customer_uq_cols
    assert {"tenant_id", "id"} in customer_uq_cols

    # Products (tenant_id, sku) and (tenant_id, id)
    product_uq_cols = [
        {col.name for col in uq.columns}
        for uq in products_table.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert {"tenant_id", "sku"} in product_uq_cols
    assert {"tenant_id", "id"} in product_uq_cols

    # Orders (tenant_id, external_order_id) and (tenant_id, id)
    order_uq_cols = [
        {col.name for col in uq.columns}
        for uq in orders_table.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert {"tenant_id", "external_order_id"} in order_uq_cols
    assert {"tenant_id", "id"} in order_uq_cols


def test_indexes_and_partial_indexes_configured():
    """Verify performance indexes, tenant_id indexes, and outbox partial index are present."""
    orders_table = Base.metadata.tables["orders"]
    order_indexes = {idx.name: [col.name for col in idx.columns] for idx in orders_table.indexes}
    assert "ix_orders_tenant_status" in order_indexes
    assert order_indexes["ix_orders_tenant_status"] == ["tenant_id", "status"]
    assert "ix_orders_tenant_status_created_at" in order_indexes
    assert order_indexes["ix_orders_tenant_status_created_at"] == ["tenant_id", "status", "created_at"]

    outbox_table = Base.metadata.tables["outbox_events"]
    unprocessed_idx = next(
        (idx for idx in outbox_table.indexes if idx.name == "ix_outbox_events_unprocessed"),
        None,
    )
    assert unprocessed_idx is not None, "Missing partial index ix_outbox_events_unprocessed"
    assert unprocessed_idx.dialect_options["postgresql"]["where"] is not None

