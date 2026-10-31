"""Unit tests for AGGRIX analytics aggregation models and schema metadata.

Verifies:
1. Model metadata registration in app.models and Base.metadata.
2. Logical aggregation unique constraints.
3. Tenant-aware single and composite foreign key constraints.
4. Monetary column precision (Numeric 14, 2) and Decimal typing.
5. Non-negative check constraints on counts, units, and monetary values.
6. Alembic migration generation consistency and offline DDL generation.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from decimal import Decimal
import pytest
import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Integer, Numeric, String, Uuid
from alembic import command
from alembic.config import Config

from app.database.base import Base
import app.models
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric


def test_analytics_models_registered_in_metadata():
    """Verify daily_tenant_metrics and daily_product_metrics tables are registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    assert "daily_tenant_metrics" in table_names, "daily_tenant_metrics must be in Base.metadata"
    assert "daily_product_metrics" in table_names, "daily_product_metrics must be in Base.metadata"

    # Verify export in app.models.__all__
    assert "DailyTenantMetric" in app.models.__all__
    assert "DailyProductMetric" in app.models.__all__
    assert getattr(app.models, "DailyTenantMetric") is DailyTenantMetric
    assert getattr(app.models, "DailyProductMetric") is DailyProductMetric


def test_primary_keys_are_uuid():
    """Verify primary keys on both analytics models use UUID types."""
    for table_name in ["daily_tenant_metrics", "daily_product_metrics"]:
        table = Base.metadata.tables[table_name]
        pk_cols = list(table.primary_key.columns)
        assert len(pk_cols) == 1, f"Expected single-column primary key on {table_name}"
        assert pk_cols[0].name == "id", f"Expected primary key 'id' on {table_name}"
        assert isinstance(pk_cols[0].type, Uuid), f"Expected UUID primary key on {table_name}"


def test_daily_tenant_metrics_columns():
    """Verify daily_tenant_metrics table columns, types, nullability, and defaults."""
    table = Base.metadata.tables["daily_tenant_metrics"]
    expected_cols = {
        "id": Uuid,
        "tenant_id": Uuid,
        "metric_date": Date,
        "currency": String,
        "orders_count": Integer,
        "gross_sales": Numeric,
        "net_sales": Numeric,
        "pending_orders_count": Integer,
        "pending_sales": Numeric,
        "cancelled_orders_count": Integer,
        "cancelled_sales": Numeric,
        "created_at": DateTime,
        "updated_at": DateTime,
    }

    for col_name, col_type in expected_cols.items():
        assert col_name in table.c, f"Column {col_name} missing from daily_tenant_metrics"
        col = table.c[col_name]
        assert isinstance(col.type, col_type), f"Column {col_name} type mismatch"
        assert not col.nullable, f"Column {col_name} should be NOT NULL"

    assert table.c["currency"].type.length == 3


def test_daily_product_metrics_columns():
    """Verify daily_product_metrics table columns, types, nullability, and defaults."""
    table = Base.metadata.tables["daily_product_metrics"]
    expected_cols = {
        "id": Uuid,
        "tenant_id": Uuid,
        "product_id": Uuid,
        "metric_date": Date,
        "currency": String,
        "units_sold_gross": Integer,
        "units_sold_net": Integer,
        "gross_sales": Numeric,
        "net_sales": Numeric,
        "pending_units": Integer,
        "pending_sales": Numeric,
        "cancelled_units": Integer,
        "cancelled_sales": Numeric,
        "orders_count": Integer,
        "created_at": DateTime,
        "updated_at": DateTime,
    }

    for col_name, col_type in expected_cols.items():
        assert col_name in table.c, f"Column {col_name} missing from daily_product_metrics"
        col = table.c[col_name]
        assert isinstance(col.type, col_type), f"Column {col_name} type mismatch"
        assert not col.nullable, f"Column {col_name} should be NOT NULL"

    assert table.c["currency"].type.length == 3


def test_monetary_column_precision_and_scale():
    """Verify all monetary columns use NUMERIC(14, 2) across both analytics tables."""
    tenant_table = Base.metadata.tables["daily_tenant_metrics"]
    for col_name in ["gross_sales", "net_sales", "cancelled_sales"]:
        col = tenant_table.c[col_name]
        assert isinstance(col.type, Numeric)
        assert col.type.precision == 14, f"{col_name} precision should be 14"
        assert col.type.scale == 2, f"{col_name} scale should be 2"

    product_table = Base.metadata.tables["daily_product_metrics"]
    for col_name in ["gross_sales", "net_sales", "cancelled_sales"]:
        col = product_table.c[col_name]
        assert isinstance(col.type, Numeric)
        assert col.type.precision == 14, f"{col_name} precision should be 14"
        assert col.type.scale == 2, f"{col_name} scale should be 2"


def test_unique_constraints():
    """Verify logical aggregation unique constraints for tenant and product daily metrics."""
    tenant_table = Base.metadata.tables["daily_tenant_metrics"]
    tenant_uqs = [
        {col.name for col in uq.columns}
        for uq in tenant_table.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert {"tenant_id", "metric_date", "currency"} in tenant_uqs, (
        "daily_tenant_metrics must enforce UNIQUE (tenant_id, metric_date, currency)"
    )

    product_table = Base.metadata.tables["daily_product_metrics"]
    product_uqs = [
        {col.name for col in uq.columns}
        for uq in product_table.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert {"tenant_id", "product_id", "metric_date", "currency"} in product_uqs, (
        "daily_product_metrics must enforce UNIQUE (tenant_id, product_id, metric_date, currency)"
    )


def test_tenant_aware_foreign_keys():
    """Verify tenant foreign keys and multi-tenant composite foreign keys."""
    # 1. daily_tenant_metrics -> tenants(id) [CASCADE]
    tenant_table = Base.metadata.tables["daily_tenant_metrics"]
    tenant_fks = [
        fk for fk in tenant_table.foreign_key_constraints
        if {col.name for col in fk.columns} == {"tenant_id"}
    ]
    assert len(tenant_fks) == 1, "daily_tenant_metrics must have FK on tenant_id"
    assert tenant_fks[0].referred_table.name == "tenants"
    assert {elem.column.name for elem in tenant_fks[0].elements} == {"id"}
    assert tenant_fks[0].ondelete.upper() == "CASCADE"

    # 2. daily_product_metrics -> tenants(id) [CASCADE]
    product_table = Base.metadata.tables["daily_product_metrics"]
    prod_tenant_fks = [
        fk for fk in product_table.foreign_key_constraints
        if {col.name for col in fk.columns} == {"tenant_id"}
    ]
    assert len(prod_tenant_fks) == 1, "daily_product_metrics must have FK on tenant_id"
    assert prod_tenant_fks[0].referred_table.name == "tenants"
    assert {elem.column.name for elem in prod_tenant_fks[0].elements} == {"id"}
    assert prod_tenant_fks[0].ondelete.upper() == "CASCADE"

    # 3. daily_product_metrics -> products(tenant_id, id) [CASCADE composite]
    prod_composite_fks = [
        fk for fk in product_table.foreign_key_constraints
        if {col.name for col in fk.columns} == {"tenant_id", "product_id"}
    ]
    assert len(prod_composite_fks) == 1, (
        "daily_product_metrics must have composite FK on (tenant_id, product_id)"
    )
    assert prod_composite_fks[0].referred_table.name == "products"
    assert {elem.column.name for elem in prod_composite_fks[0].elements} == {"tenant_id", "id"}
    assert prod_composite_fks[0].ondelete.upper() == "CASCADE"


def test_non_negative_check_constraints():
    """Verify database-level check constraints enforce non-negative counts, units, and sales."""
    tenant_table = Base.metadata.tables["daily_tenant_metrics"]
    tenant_cks = [c.sqltext.text for c in tenant_table.constraints if isinstance(c, sa.CheckConstraint)]
    assert any("orders_count >= 0" in text for text in tenant_cks)
    assert any("gross_sales >= 0" in text for text in tenant_cks)
    assert any("net_sales >= 0" in text for text in tenant_cks)
    assert any("cancelled_orders_count >= 0" in text for text in tenant_cks)
    assert any("cancelled_sales >= 0" in text for text in tenant_cks)

    product_table = Base.metadata.tables["daily_product_metrics"]
    prod_cks = [c.sqltext.text for c in product_table.constraints if isinstance(c, sa.CheckConstraint)]
    assert any("units_sold_gross >= 0" in text for text in prod_cks)
    assert any("units_sold_net >= 0" in text for text in prod_cks)
    assert any("gross_sales >= 0" in text for text in prod_cks)
    assert any("net_sales >= 0" in text for text in prod_cks)
    assert any("cancelled_units >= 0" in text for text in prod_cks)
    assert any("cancelled_sales >= 0" in text for text in prod_cks)
    assert any("orders_count >= 0" in text for text in prod_cks)


def test_indexes_configured():
    """Verify performance indexes on tenant_id/date and tenant_id/product_id/date."""
    tenant_table = Base.metadata.tables["daily_tenant_metrics"]
    tenant_idx_cols = [[c.name for c in idx.columns] for idx in tenant_table.indexes]
    assert ["tenant_id", "metric_date"] in tenant_idx_cols

    product_table = Base.metadata.tables["daily_product_metrics"]
    prod_idx_cols = [[c.name for c in idx.columns] for idx in product_table.indexes]
    assert ["tenant_id", "metric_date"] in prod_idx_cols
    assert ["tenant_id", "product_id", "metric_date"] in prod_idx_cols
    assert ["tenant_id", "product_id"] in prod_idx_cols


def test_migration_generation_consistency():
    """Verify the Alembic migration file for analytics tables exists and is consistent."""
    versions_dir = Path("alembic/versions")
    assert versions_dir.exists()
    migration_files = list(versions_dir.glob("*.py"))

    # Initial migration + analytics migration
    assert len(migration_files) >= 2, "Expected at least 2 migration versions"
    analytics_migrations = [f for f in migration_files if "aggregation_tables" in f.name]
    assert len(analytics_migrations) == 1, "Expected exactly 1 analytics aggregation tables migration file"

    migration_content = analytics_migrations[0].read_text()
    assert "0001_initial_schema" in migration_content, "Down revision must be 0001_initial_schema"
    assert "daily_tenant_metrics" in migration_content
    assert "daily_product_metrics" in migration_content
    assert "fk_daily_product_metrics_product_tenant" in migration_content
    assert "uq_daily_product_metrics_tenant_product_date_currency" in migration_content
    assert "uq_daily_tenant_metrics_tenant_date_currency" in migration_content


def test_alembic_offline_migration_ddl_for_analytics_tables():
    """Verify Alembic executes offline migration up to head and outputs analytics DDL."""
    alembic_cfg = Config("alembic.ini")
    buffer = io.StringIO()

    with contextlib.redirect_stdout(buffer):
        command.upgrade(alembic_cfg, "head", sql=True)

    generated_sql = buffer.getvalue()

    # Both analytics tables must be in the generated DDL
    assert "CREATE TABLE daily_tenant_metrics" in generated_sql
    assert "CREATE TABLE daily_product_metrics" in generated_sql

    # Verify composite FK in generated DDL
    assert (
        "CONSTRAINT fk_daily_product_metrics_product_tenant "
        "FOREIGN KEY(tenant_id, product_id) REFERENCES products (tenant_id, id) "
        "ON DELETE CASCADE" in generated_sql
    )

    # Verify unique constraints in generated DDL
    assert (
        "CONSTRAINT uq_daily_tenant_metrics_tenant_date_currency "
        "UNIQUE (tenant_id, metric_date, currency)" in generated_sql
    )
    assert (
        "CONSTRAINT uq_daily_product_metrics_tenant_product_date_currency "
        "UNIQUE (tenant_id, product_id, metric_date, currency)" in generated_sql
    )


def test_live_database_revision_matches_head():
    """Verify the live database has been upgraded to head revision."""
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from app.database.connection import engine

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    head_rev = script.get_current_head()

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        assert current_rev == head_rev, (
            f"Live database must be at head revision {head_rev}, but is at {current_rev}"
        )


def test_tenant_timezone_column_and_seeding():
    """Verify tenants table contains timezone column and existing tenants are configured."""
    from app.database.connection import engine

    tenants_table = Base.metadata.tables["tenants"]
    assert "timezone" in tenants_table.c
    assert isinstance(tenants_table.c["timezone"].type, String)
    assert not tenants_table.c["timezone"].nullable

    with engine.connect() as conn:
        tzs = conn.execute(sa.text("SELECT domain, timezone FROM tenants")).fetchall()
        for domain, tz in tzs:
            assert tz is not None and tz != "", f"Tenant {domain} must have an explicit timezone"


def test_analytics_consumer_events_table_schema():
    """Verify analytics_consumer_events table schema, composite PK, and indexes."""
    table = Base.metadata.tables["analytics_consumer_events"]
    assert {"consumer_name", "event_id"} == {c.name for c in table.primary_key.columns}

    # Foreign key to tenants
    fks = list(table.foreign_key_constraints)
    assert len(fks) == 1
    assert fks[0].referred_table.name == "tenants"
    assert fks[0].ondelete.upper() == "CASCADE"

    # Indexes
    idx_names = {idx.name for idx in table.indexes}
    assert "ix_analytics_consumer_events_consumer_tenant" in idx_names
    assert "ix_analytics_consumer_events_consumer_order" in idx_names


