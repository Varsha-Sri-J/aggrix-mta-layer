"""Command Line Interface for AGGRIX Synthetic E-commerce Data Generator.

Usage:
    # Full generation against database
    python -m app.generator.cli --tenants 5 --customers-per-tenant 500 --products-per-tenant 100 --orders-per-tenant 2000 --seed 42

    # In-memory validation dry run (no database writes)
    python -m app.generator.cli --dry-run --tenants 2 --orders-per-tenant 50

    # Safe synthetic data cleanup (with preview and explicit confirmation)
    python -m app.generator.cli --cleanup
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure backend directory is in sys.path when executed directly as a script
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database.connection import create_database_engine, get_db_session
from app.generator.config import SYNTHETIC_DOMAIN_SUFFIX, GeneratorConfig
from app.generator.engine import SyntheticDataGenerator


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI options for data generation."""
    parser = argparse.ArgumentParser(
        description="AGGRIX Synthetic E-commerce Data Generator CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--tenants",
        type=int,
        default=5,
        help="Number of tenants to generate",
    )
    parser.add_argument(
        "--customers-per-tenant",
        type=int,
        default=500,
        help="Number of customers per tenant",
    )
    parser.add_argument(
        "--products-per-tenant",
        type=int,
        default=100,
        help="Number of products per tenant",
    )
    parser.add_argument(
        "--orders-per-tenant",
        type=int,
        default=2000,
        help="Number of orders per tenant",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for chunked database insertions",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic repeatability",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Number of historical days to distribute records across",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="ISO-8601 reference timestamp (e.g. '2026-10-31T12:00:00Z') for exact reproducible runs",
    )
    parser.add_argument(
        "--unprocessed-ratio",
        type=float,
        default=0.10,
        help="Fraction of outbox events left in pending state (processed_at = NULL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate in-memory only; do not write to the database",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Preview and safely purge synthetic tenants and cascaded records",
    )
    parser.add_argument(
        "--domain-pattern",
        type=str,
        default=None,
        help=f"SQL LIKE pattern for synthetic tenant domains (strictly within *.{SYNTHETIC_DOMAIN_SUFFIX})",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically confirm synthetic data cleanup without interactive prompt",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Run in incremental expansion mode (preserves existing dataset and auto-offsets)",
    )
    parser.add_argument(
        "--tenant-offset",
        type=int,
        default=None,
        help="Starting tenant index sequence offset (auto-detected if in --incremental mode)",
    )
    parser.add_argument(
        "--customer-offset",
        type=int,
        default=0,
        help="Starting customer email sequence offset per tenant",
    )
    parser.add_argument(
        "--product-offset",
        type=int,
        default=0,
        help="Starting product SKU sequence offset per tenant",
    )
    parser.add_argument(
        "--order-offset",
        type=int,
        default=0,
        help="Starting order sequence offset (SHP-{order_offset + seq:06d})",
    )
    parser.add_argument(
        "--commit-per-tenant",
        action="store_true",
        help="Commit database transaction and expunge session after each tenant partition for O(1) memory",
    )
    parser.add_argument(
        "--all-unprocessed",
        action="store_true",
        help="Mark 100%% of generated outbox events as pending (processed_at = NULL) for live analytics worker",
    )
    parser.add_argument(
        "--target-tenant-id",
        type=str,
        default=None,
        help="Target a specific existing tenant UUID to append customers/products/orders to",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Explicit database URL override",
    )
    return parser.parse_args(args)


def parse_as_of(as_of_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 string to timezone-aware UTC datetime."""
    if not as_of_str:
        return None
    dt = datetime.fromisoformat(as_of_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main(args: list[str] | None = None) -> int:
    """Entry point for CLI execution."""
    opts = parse_args(args)
    as_of_dt = parse_as_of(opts.as_of)

    tenant_offset = opts.tenant_offset
    if tenant_offset is None and opts.incremental:
        try:
            with get_db_session() as session:
                tenant_offset = SyntheticDataGenerator.detect_synthetic_tenant_count(session)
        except Exception:
            tenant_offset = 0
    elif tenant_offset is None:
        tenant_offset = 0

    config = GeneratorConfig(
        tenants_count=opts.tenants,
        customers_per_tenant=opts.customers_per_tenant,
        products_per_tenant=opts.products_per_tenant,
        orders_per_tenant=opts.orders_per_tenant,
        batch_size=opts.batch_size,
        seed=opts.seed,
        days_history=opts.days,
        as_of=as_of_dt,
        unprocessed_outbox_percentage=opts.unprocessed_ratio,
        tenant_offset=tenant_offset,
        customer_offset=opts.customer_offset,
        product_offset=opts.product_offset,
        order_offset=opts.order_offset,
        incremental=opts.incremental,
        commit_per_tenant=opts.commit_per_tenant,
        all_outbox_unprocessed=opts.all_unprocessed,
        existing_tenant_id=opts.target_tenant_id,
    )
    config.validate()

    generator = SyntheticDataGenerator(config=config)

    # 1. Cleanup mode
    if opts.cleanup:
        pattern = opts.domain_pattern or f"%.{SYNTHETIC_DOMAIN_SUFFIX}"
        print(f"[*] Inspecting database for synthetic records matching pattern: '{pattern}'...")

        with get_db_session() as session:
            try:
                plan = generator.preview_cleanup_synthetic_data(session=session, domain_pattern=pattern)
            except ValueError as err:
                print(f"[!] Safety Error: {err}")
                return 1

            if plan.tenants_count == 0:
                print(f"[+] No synthetic tenants found matching '{pattern}'. Database is clean.")
                return 0

            print("\n" + "=" * 60)
            print("SYNTHETIC DATA CLEANUP IMPACT PREVIEW")
            print("=" * 60)
            print(f"Domain Pattern:        {plan.domain_pattern}")
            print(f"Synthetic Tenants:     {plan.tenants_count:,}")
            print(f"Customers:             {plan.customers_count:,}")
            print(f"Products:              {plan.products_count:,}")
            print(f"Orders:                {plan.orders_count:,}")
            print(f"Order Items:           {plan.order_items_count:,}")
            print(f"Outbox Events:         {plan.outbox_events_count:,}")
            print(f"Total Records Impact:  {plan.total_records_count:,}")
            print("=" * 60)

            # Check confirmation
            confirmed = opts.yes
            if not confirmed:
                try:
                    user_input = input("\n[?] Confirm deletion of the above synthetic records? [y/N]: ").strip().lower()
                    confirmed = (user_input in ("y", "yes"))
                except EOFError:
                    confirmed = False

            if not confirmed:
                print("[!] Cleanup cancelled by user. Zero records were modified.\n")
                return 0

            # Execute safe deletion
            generator.cleanup_synthetic_data(session=session, domain_pattern=pattern, confirm=True)
            print(f"[+] Cleanup successfully executed: Purged {plan.tenants_count} tenants and {plan.total_records_count:,} total records.\n")
        return 0

    # 2. Dry run mode
    if opts.dry_run:
        ref_time = config.get_reference_time().isoformat()
        if opts.incremental:
            with get_db_session() as session:
                preview = generator.preview_incremental_generation(session=session)

            print("\n" + "=" * 80)
            print("AGGRIX SYNTHETIC DATA GENERATION: INCREMENTAL DRY RUN PREVIEW")
            print("=" * 80)
            print(f"Reference Time:         {ref_time}")
            print(f"Tenant Offset:          {preview.tenant_offset}")
            print(f"Target New Tenants:     {preview.planned_tenants_count:,}")
            if preview.colliding_domains:
                print(f"[!] WARNING: {len(preview.colliding_domains)} domain collision(s) detected: {preview.colliding_domains}")
            print("-" * 80)
            print(f"{'Entity':<18} {'Current DB':<20} {'Planned New':<20} {'Projected Total':<20}")
            print("-" * 80)
            print(f"{'Tenants':<18} {preview.existing_tenants_count:<20,} {preview.planned_tenants_count:<20,} {preview.existing_tenants_count + preview.planned_tenants_count:<20,}")
            print(f"{'Customers':<18} {preview.existing_customers_count:<20,} {preview.planned_customers_count:<20,} {preview.existing_customers_count + preview.planned_customers_count:<20,}")
            print(f"{'Products':<18} {preview.existing_products_count:<20,} {preview.planned_products_count:<20,} {preview.existing_products_count + preview.planned_products_count:<20,}")
            print(f"{'Orders':<18} {preview.existing_orders_count:<20,} {preview.planned_orders_count:<20,} {preview.existing_orders_count + preview.planned_orders_count:<20,}")
            print(f"{'Order Items':<18} {preview.existing_order_items_count:<20,} ~{preview.planned_order_items_count:<19,} ~{preview.existing_order_items_count + preview.planned_order_items_count:<19,}")
            print(f"{'Outbox Events':<18} {preview.existing_outbox_events_count:<20,} ~{preview.planned_outbox_events_count:<19,} ~{preview.existing_outbox_events_count + preview.planned_outbox_events_count:<19,}")
            print(f"  Pending Outbox:       ~{preview.planned_unprocessed_outbox_count:,} events flagged for live worker processing")
            print("=" * 80)
            print("[+] Incremental dry run succeeded with 0 database modifications.\n")
            return 0

        # In-memory only dry run
        print(f"[*] Running DRY RUN generation (seed={config.seed}, as_of={ref_time})...")
        dataset = generator.generate_dataset()
        stats = dataset.stats

        print("\n" + "=" * 60)
        print("AGGRIX SYNTHETIC DATA GENERATION (DRY RUN SUMMARY)")
        print("=" * 60)
        print(f"Reference Time:    {ref_time}")
        print(f"Tenants:           {stats.tenants_count:,}")
        print(f"Customers:         {stats.customers_count:,}")
        print(f"Products:          {stats.products_count:,}")
        print(f"Orders:            {stats.orders_count:,}")
        print(f"Order Items:       {stats.order_items_count:,}")
        print(f"Outbox Events:     {stats.outbox_events_count:,} ({stats.unprocessed_outbox_count:,} pending)")
        print(f"Total Revenue:     ${stats.total_revenue:,.2f}")
        print(f"Status Breakdown:  {stats.status_counts}")
        print(f"Generation Time:   {stats.generation_seconds:.2f}s")
        print("=" * 60)
        print("[+] Dry run succeeded with 0 database modifications.\n")
        return 0

    # 3. Live database generation
    ref_time = config.get_reference_time().isoformat()
    print(f"[*] Starting live generation and database insertion (seed={config.seed}, as_of={ref_time})...")
    if opts.target_tenant_id:
        print(f"    Target Tenant: {opts.target_tenant_id} (appending records)")
    else:
        print(
            f"    Target: {config.tenants_count} tenants (offset={config.tenant_offset}), "
            f"{config.customers_per_tenant} customers/tenant, "
            f"{config.products_per_tenant} products/tenant, "
            f"{config.orders_per_tenant} orders/tenant"
        )

    with get_db_session() as session:
        if opts.target_tenant_id:
            import uuid
            stats = generator.insert_incremental_for_tenant(
                session=session,
                tenant_id=uuid.UUID(opts.target_tenant_id),
            )
        elif opts.incremental or opts.commit_per_tenant:
            stats = generator.insert_dataset_streaming(
                session=session,
                commit_per_tenant=opts.commit_per_tenant,
            )
        else:
            stats = generator.insert_dataset(session=session)

    print("\n" + "=" * 60)
    print("AGGRIX SYNTHETIC DATA GENERATION COMPLETE")
    print("=" * 60)
    print(f"Reference Time:         {ref_time}")
    print(f"Mode:                   {'Incremental' if opts.incremental else 'Full'}")
    print(f"Tenants Inserted:       {stats.tenants_count:,}")
    print(f"Customers Inserted:     {stats.customers_count:,}")
    print(f"Products Inserted:      {stats.products_count:,}")
    print(f"Orders Inserted:        {stats.orders_count:,}")
    print(f"Order Items Inserted:   {stats.order_items_count:,}")
    print(f"Outbox Events Inserted: {stats.outbox_events_count:,} ({stats.unprocessed_outbox_count:,} pending)")
    print(f"Total Gross Revenue:    ${stats.total_revenue:,.2f}")
    print(f"Status Breakdown:       {stats.status_counts}")
    print(f"Generation Time:        {stats.generation_seconds:.2f}s")
    print(f"Insertion Time:         {stats.insertion_seconds:.2f}s")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
