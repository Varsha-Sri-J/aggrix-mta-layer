"""Alembic migration generation and DDL verification tests."""

import contextlib
import io
from pathlib import Path
from alembic import command
from alembic.config import Config


def test_migration_version_file_exists():
    """Verify that the initial migration script exists in alembic/versions/."""
    versions_dir = Path("alembic/versions")
    assert versions_dir.exists()
    migration_files = list(versions_dir.glob("*.py"))
    assert len(migration_files) >= 1, "At least one migration file should exist"
    assert any("initial_schema" in f.name for f in migration_files)


def test_alembic_offline_migration_ddl_generation():
    """Verify Alembic executes offline migration without error and outputs valid DDL."""
    alembic_cfg = Config("alembic.ini")
    buffer = io.StringIO()

    # Capture standard output emitted during offline migration
    with contextlib.redirect_stdout(buffer):
        command.upgrade(alembic_cfg, "head", sql=True)

    generated_sql = buffer.getvalue()

    # Verify all 6 tables are in the generated DDL
    expected_tables = [
        "CREATE TABLE tenants",
        "CREATE TABLE customers",
        "CREATE TABLE products",
        "CREATE TABLE orders",
        "CREATE TABLE order_items",
        "CREATE TABLE outbox_events",
    ]
    for table_ddl in expected_tables:
        assert table_ddl in generated_sql, f"Missing table DDL: {table_ddl}"

    # Verify composite foreign keys are in the generated DDL
    assert "CONSTRAINT fk_orders_customer_tenant FOREIGN KEY(tenant_id, customer_id) REFERENCES customers (tenant_id, id)" in generated_sql
    assert "CONSTRAINT fk_order_items_order_tenant FOREIGN KEY(tenant_id, order_id) REFERENCES orders (tenant_id, id)" in generated_sql
    assert "CONSTRAINT fk_order_items_product_tenant FOREIGN KEY(tenant_id, product_id) REFERENCES products (tenant_id, id)" in generated_sql

    # Verify partial index for outbox events is present
    assert "CREATE INDEX ix_outbox_events_unprocessed ON outbox_events (created_at) WHERE processed_at IS NULL" in generated_sql
