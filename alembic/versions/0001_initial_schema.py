"""Initial schema migration for AGGRIX multi-tenant database.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-10-31 13:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Tenants Table
    # -------------------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("domain", name="uq_tenants_domain"),
    )
    op.create_index(op.f("ix_tenants_domain"), "tenants", ["domain"], unique=True)

    # -------------------------------------------------------------------------
    # 2. Customers Table
    # -------------------------------------------------------------------------
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_customers_tenant_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_customers_tenant_id_email"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"], unique=False)
    op.create_index("ix_customers_email", "customers", ["email"], unique=False)

    # -------------------------------------------------------------------------
    # 3. Products Table
    # -------------------------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_products_tenant_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_id_sku"),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"], unique=False)
    op.create_index("ix_products_sku", "products", ["sku"], unique=False)

    # -------------------------------------------------------------------------
    # 4. Orders Table
    # -------------------------------------------------------------------------
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("external_order_id", sa.String(length=255), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_orders_tenant_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            ondelete="RESTRICT",
            name="fk_orders_customer_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_orders_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "external_order_id",
            name="uq_orders_tenant_id_external_order_id",
        ),
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"], unique=False)
    op.create_index("ix_orders_tenant_status", "orders", ["tenant_id", "status"], unique=False)
    op.create_index("ix_orders_tenant_created_at", "orders", ["tenant_id", "created_at"], unique=False)
    op.create_index(
        "ix_orders_tenant_status_created_at",
        "orders",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_orders_tenant_customer_id",
        "orders",
        ["tenant_id", "customer_id"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 5. Order Items Table
    # -------------------------------------------------------------------------
    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_order_items_tenant_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            ondelete="CASCADE",
            name="fk_order_items_order_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            ondelete="RESTRICT",
            name="fk_order_items_product_tenant",
        ),
    )
    op.create_index("ix_order_items_tenant_id", "order_items", ["tenant_id"], unique=False)
    op.create_index(
        "ix_order_items_tenant_order_id",
        "order_items",
        ["tenant_id", "order_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_items_tenant_product_id",
        "order_items",
        ["tenant_id", "product_id"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 6. Outbox Events Table
    # -------------------------------------------------------------------------
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name="fk_outbox_events_tenant_id",
        ),
    )
    op.create_index("ix_outbox_events_tenant_id", "outbox_events", ["tenant_id"], unique=False)
    op.create_index(
        "ix_outbox_events_unprocessed",
        "outbox_events",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_index("ix_outbox_events_processed_at", "outbox_events", ["processed_at"], unique=False)
    op.create_index(
        "ix_outbox_events_tenant_created",
        "outbox_events",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("products")
    op.drop_table("customers")
    op.drop_table("tenants")

