"""Orchestration engine for AGGRIX Synthetic E-commerce Data Generator.

Manages deterministic dataset generation, chunked batch database insertion,
transaction safety, safe synthetic namespace cleanup, and streaming architecture
for multi-million record scalability.
"""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Generator, Iterable, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.generator.builders import (
    build_customers,
    build_order_and_items,
    build_products,
    build_tenant,
)
from app.generator.config import SYNTHETIC_DOMAIN_SUFFIX, GeneratorConfig
from app.generator.providers import STORE_NAMES, slugify
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant


@dataclass
class IncrementalDryRunPreview:
    """Preview of current database state vs planned incremental additions."""

    existing_tenants_count: int = 0
    existing_customers_count: int = 0
    existing_products_count: int = 0
    existing_orders_count: int = 0
    existing_order_items_count: int = 0
    existing_outbox_events_count: int = 0

    planned_tenants_count: int = 0
    planned_customers_count: int = 0
    planned_products_count: int = 0
    planned_orders_count: int = 0
    planned_order_items_count: int = 0
    planned_outbox_events_count: int = 0
    planned_unprocessed_outbox_count: int = 0

    tenant_offset: int = 0
    colliding_domains: List[str] = field(default_factory=list)


@dataclass
class GeneratorStats:
    """Summary metrics of generated synthetic data."""

    tenants_count: int = 0
    customers_count: int = 0
    products_count: int = 0
    orders_count: int = 0
    order_items_count: int = 0
    outbox_events_count: int = 0
    unprocessed_outbox_count: int = 0
    total_revenue: Decimal = Decimal("0.00")
    status_counts: Dict[str, int] = field(default_factory=dict)
    generation_seconds: float = 0.0
    insertion_seconds: float = 0.0


@dataclass
class TenantData:
    """In-memory representation of a single tenant and all its child records."""

    tenant: Tenant
    customers: List[Customer] = field(default_factory=list)
    products: List[Product] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    order_items: List[OrderItem] = field(default_factory=list)
    outbox_events: List[OutboxEvent] = field(default_factory=list)


@dataclass
class GeneratorDataset:
    """In-memory representation of generated synthetic records."""

    tenants: List[Tenant] = field(default_factory=list)
    customers: List[Customer] = field(default_factory=list)
    products: List[Product] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    order_items: List[OrderItem] = field(default_factory=list)
    outbox_events: List[OutboxEvent] = field(default_factory=list)
    stats: GeneratorStats = field(default_factory=GeneratorStats)


@dataclass
class CleanupPlan:
    """Preview impact analysis of synthetic records targeted for cleanup."""

    domain_pattern: str
    tenant_ids: List[uuid.UUID] = field(default_factory=list)
    tenants_count: int = 0
    customers_count: int = 0
    products_count: int = 0
    orders_count: int = 0
    order_items_count: int = 0
    outbox_events_count: int = 0
    confirmed: bool = False
    deleted: bool = False

    @property
    def total_records_count(self) -> int:
        """Sum of all records across the six models that will be deleted."""
        return (
            self.tenants_count
            + self.customers_count
            + self.products_count
            + self.orders_count
            + self.order_items_count
            + self.outbox_events_count
        )


def chunked(iterable: Iterable, chunk_size: int) -> Generator[List, None, None]:
    """Yield successive chunk_size slices from an iterable."""
    chunk: List = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


class SyntheticDataGenerator:
    """Deterministic, multi-tenant synthetic data generator for AGGRIX."""

    def __init__(self, config: Optional[GeneratorConfig] = None) -> None:
        self.config = config or GeneratorConfig()
        self.config.validate()
        self.rng = random.Random(self.config.seed)

    def _generate_single_tenant_data(
        self,
        tenant_index: int,
        reference_time: datetime,
    ) -> TenantData:
        """Generate models for a single tenant and its complete child partition."""
        tenant = build_tenant(self.rng, tenant_index, reference_time, self.config)
        customers = build_customers(
            self.rng,
            tenant.id,
            self.config.customers_per_tenant,
            reference_time,
            self.config,
            customer_offset=self.config.customer_offset,
        )
        products = build_products(
            self.rng,
            tenant.id,
            self.config.products_per_tenant,
            reference_time,
            self.config,
            product_offset=self.config.product_offset,
        )

        orders: List[Order] = []
        order_items: List[OrderItem] = []
        outbox_events: List[OutboxEvent] = []

        for o_idx in range(self.config.orders_per_tenant):
            customer = self.rng.choice(customers)
            order, items, events = build_order_and_items(
                self.rng,
                tenant.id,
                customer,
                products,
                order_seq=self.config.order_offset + o_idx + 1,
                base_time=reference_time,
                config=self.config,
            )
            orders.append(order)
            order_items.extend(items)
            outbox_events.extend(events)

        return TenantData(
            tenant=tenant,
            customers=customers,
            products=products,
            orders=orders,
            order_items=order_items,
            outbox_events=outbox_events,
        )

    def generate_tenant_stream(
        self,
        base_time: Optional[datetime] = None,
    ) -> Generator[TenantData, None, None]:
        """Incremental streaming generator yielding one tenant's partition at a time.

        Architectural Foundation for Million-Record Scaling:
        Unlike in-memory collection which holds all records in RAM simultaneously,
        streaming tenant-by-tenant allows generating and committing millions of records
        with constant O(1) memory overhead.
        """
        reference_time = base_time or self.config.get_reference_time()
        for t_idx in range(self.config.tenants_count):
            effective_idx = self.config.tenant_offset + t_idx
            yield self._generate_single_tenant_data(effective_idx, reference_time)

    def generate_dataset(
        self,
        base_time: Optional[datetime] = None,
    ) -> GeneratorDataset:
        """Generate complete synthetic dataset in memory without database writes.

        Args:
            base_time: Optional reference timestamp. If None, uses config.as_of or UTC now.

        Returns:
            GeneratorDataset containing all models and statistical metrics.
        """
        start_time = time.perf_counter()
        reference_time = base_time or self.config.get_reference_time()

        dataset = GeneratorDataset()
        stats = dataset.stats

        status_counts: Dict[str, int] = {}
        total_revenue = Decimal("0.00")

        for tenant_data in self.generate_tenant_stream(base_time=reference_time):
            dataset.tenants.append(tenant_data.tenant)
            dataset.customers.extend(tenant_data.customers)
            dataset.products.extend(tenant_data.products)
            dataset.orders.extend(tenant_data.orders)
            dataset.order_items.extend(tenant_data.order_items)
            dataset.outbox_events.extend(tenant_data.outbox_events)

            for order in tenant_data.orders:
                total_revenue += order.total_amount
                status_counts[order.status] = status_counts.get(order.status, 0) + 1

        unprocessed_events = sum(1 for e in dataset.outbox_events if e.processed_at is None)

        stats.tenants_count = len(dataset.tenants)
        stats.customers_count = len(dataset.customers)
        stats.products_count = len(dataset.products)
        stats.orders_count = len(dataset.orders)
        stats.order_items_count = len(dataset.order_items)
        stats.outbox_events_count = len(dataset.outbox_events)
        stats.unprocessed_outbox_count = unprocessed_events
        stats.total_revenue = total_revenue
        stats.status_counts = status_counts
        stats.generation_seconds = time.perf_counter() - start_time

        return dataset

    def insert_dataset(
        self,
        session: Session,
        dataset: Optional[GeneratorDataset] = None,
        base_time: Optional[datetime] = None,
    ) -> GeneratorStats:
        """Insert synthetic dataset into database using chunked batch transactions.

        Follows strict topological ordering:
        1. Tenants
        2. Customers
        3. Products
        4. Orders
        5. OrderItems
        6. OutboxEvents

        Args:
            session: Active SQLAlchemy database session.
            dataset: Pre-generated dataset. If None, generates from config.
            base_time: Optional base timestamp if generating dataset on-the-fly.

        Returns:
            GeneratorStats containing summary metrics and execution timing.
        """
        if dataset is None:
            dataset = self.generate_dataset(base_time=base_time)

        start_time = time.perf_counter()
        batch_size = self.config.batch_size

        try:
            # 1. Tenants
            session.add_all(dataset.tenants)
            session.flush()

            # 2. Customers (chunked)
            for chunk in chunked(dataset.customers, batch_size):
                session.add_all(chunk)
                session.flush()

            # 3. Products (chunked)
            for chunk in chunked(dataset.products, batch_size):
                session.add_all(chunk)
                session.flush()

            # 4. Orders (chunked)
            for chunk in chunked(dataset.orders, batch_size):
                session.add_all(chunk)
                session.flush()

            # 5. OrderItems (chunked)
            for chunk in chunked(dataset.order_items, batch_size):
                session.add_all(chunk)
                session.flush()

            # 6. OutboxEvents (chunked)
            for chunk in chunked(dataset.outbox_events, batch_size):
                session.add_all(chunk)
                session.flush()

            session.commit()
        except Exception:
            session.rollback()
            raise

        dataset.stats.insertion_seconds = time.perf_counter() - start_time
        return dataset.stats

    def check_duplicate_prevention(self, session: Session) -> List[str]:
        """Check whether any candidate tenant domain already exists in the database.

        Returns a list of colliding domains, if any.
        """
        candidate_domains: List[str] = []
        for t_idx in range(self.config.tenants_count):
            effective_idx = self.config.tenant_offset + t_idx
            name_template = STORE_NAMES[effective_idx % len(STORE_NAMES)]
            suffix = f" {effective_idx + 1}" if effective_idx >= len(STORE_NAMES) else ""
            store_name = f"{name_template}{suffix}"
            slug = slugify(store_name)
            candidate_domains.append(f"{slug}.{self.config.domain_suffix}")

        if not candidate_domains:
            return []

        stmt = select(Tenant.domain).where(Tenant.domain.in_(candidate_domains))
        return list(session.execute(stmt).scalars().all())

    @classmethod
    def detect_synthetic_tenant_count(
        cls,
        session: Session,
        domain_suffix: str = SYNTHETIC_DOMAIN_SUFFIX,
    ) -> int:
        """Count existing synthetic tenants in database matching domain pattern."""
        pattern = f"%.{domain_suffix}"
        return session.execute(
            select(func.count()).select_from(Tenant).where(Tenant.domain.like(pattern))
        ).scalar() or 0

    def preview_incremental_generation(self, session: Session) -> IncrementalDryRunPreview:
        """Inspect active database and compute planned incremental insertion metrics."""
        t_count = session.execute(select(func.count()).select_from(Tenant)).scalar() or 0
        c_count = session.execute(select(func.count()).select_from(Customer)).scalar() or 0
        p_count = session.execute(select(func.count()).select_from(Product)).scalar() or 0
        o_count = session.execute(select(func.count()).select_from(Order)).scalar() or 0
        oi_count = session.execute(select(func.count()).select_from(OrderItem)).scalar() or 0
        oe_count = session.execute(select(func.count()).select_from(OutboxEvent)).scalar() or 0

        colliding = self.check_duplicate_prevention(session=session) if self.config.existing_tenant_id is None else []

        planned_t = 0 if self.config.existing_tenant_id else self.config.tenants_count
        target_tenants = 1 if self.config.existing_tenant_id else self.config.tenants_count
        planned_c = target_tenants * self.config.customers_per_tenant
        planned_p = target_tenants * self.config.products_per_tenant
        planned_o = target_tenants * self.config.orders_per_tenant

        avg_items = (self.config.min_items_per_order + self.config.max_items_per_order) / 2.0
        planned_oi = int(planned_o * avg_items)
        planned_oe = int(planned_o * 2.55)
        planned_unprocessed = (
            planned_oe if self.config.all_outbox_unprocessed
            else int(planned_oe * self.config.unprocessed_outbox_percentage)
        )

        return IncrementalDryRunPreview(
            existing_tenants_count=t_count,
            existing_customers_count=c_count,
            existing_products_count=p_count,
            existing_orders_count=o_count,
            existing_order_items_count=oi_count,
            existing_outbox_events_count=oe_count,
            planned_tenants_count=planned_t,
            planned_customers_count=planned_c,
            planned_products_count=planned_p,
            planned_orders_count=planned_o,
            planned_order_items_count=planned_oi,
            planned_outbox_events_count=planned_oe,
            planned_unprocessed_outbox_count=planned_unprocessed,
            tenant_offset=self.config.tenant_offset,
            colliding_domains=colliding,
        )

    def generate_incremental_for_tenant(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        base_time: Optional[datetime] = None,
        new_customers_count: Optional[int] = None,
        new_products_count: Optional[int] = None,
        new_orders_count: Optional[int] = None,
    ) -> TenantData:
        """Generate incremental records for an existing tenant."""
        reference_time = base_time or self.config.get_reference_time()
        tenant = session.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id} not found in database.")

        existing_customers = list(session.execute(select(Customer).where(Customer.tenant_id == tenant_id)).scalars().all())
        existing_products = list(session.execute(select(Product).where(Product.tenant_id == tenant_id)).scalars().all())

        c_count = new_customers_count if new_customers_count is not None else (
            self.config.customers_per_tenant if self.config.existing_tenant_id else 0
        )
        new_customers: List[Customer] = []
        if c_count > 0:
            new_customers = build_customers(
                self.rng,
                tenant.id,
                c_count,
                reference_time,
                self.config,
                customer_offset=len(existing_customers),
            )

        all_customers = existing_customers + new_customers
        if not all_customers:
            raise ValueError(f"Tenant {tenant_id} has no customers. Please generate customers first.")

        p_count = new_products_count if new_products_count is not None else (
            self.config.products_per_tenant if self.config.existing_tenant_id else 0
        )
        new_products: List[Product] = []
        if p_count > 0:
            new_products = build_products(
                self.rng,
                tenant.id,
                p_count,
                reference_time,
                self.config,
                product_offset=len(existing_products),
            )

        all_products = existing_products + new_products
        if not all_products:
            raise ValueError(f"Tenant {tenant_id} has no products. Please generate products first.")

        existing_orders_count = session.execute(
            select(func.count()).select_from(Order).where(Order.tenant_id == tenant_id)
        ).scalar() or 0
        order_offset = max(self.config.order_offset, existing_orders_count)

        orders_count = new_orders_count if new_orders_count is not None else self.config.orders_per_tenant
        new_orders: List[Order] = []
        new_items: List[OrderItem] = []
        new_events: List[OutboxEvent] = []

        for o_idx in range(orders_count):
            cust = self.rng.choice(all_customers)
            order, items, events = build_order_and_items(
                self.rng,
                tenant.id,
                cust,
                all_products,
                order_seq=order_offset + o_idx + 1,
                base_time=reference_time,
                config=self.config,
            )
            new_orders.append(order)
            new_items.extend(items)
            new_events.extend(events)

        return TenantData(
            tenant=tenant,
            customers=new_customers,
            products=new_products,
            orders=new_orders,
            order_items=new_items,
            outbox_events=new_events,
        )

    def insert_incremental_for_tenant(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        base_time: Optional[datetime] = None,
        new_customers_count: Optional[int] = None,
        new_products_count: Optional[int] = None,
        new_orders_count: Optional[int] = None,
    ) -> GeneratorStats:
        """Insert incremental records for an existing tenant."""
        start_time = time.perf_counter()
        batch_size = self.config.batch_size
        data = self.generate_incremental_for_tenant(
            session=session,
            tenant_id=tenant_id,
            base_time=base_time,
            new_customers_count=new_customers_count,
            new_products_count=new_products_count,
            new_orders_count=new_orders_count,
        )

        stats = GeneratorStats()
        status_counts: Dict[str, int] = {}
        total_revenue = Decimal("0.00")
        unprocessed_events = 0

        try:
            for chunk in chunked(data.customers, batch_size):
                session.add_all(chunk)
                session.flush()

            for chunk in chunked(data.products, batch_size):
                session.add_all(chunk)
                session.flush()

            for chunk in chunked(data.orders, batch_size):
                session.add_all(chunk)
                session.flush()

            for chunk in chunked(data.order_items, batch_size):
                session.add_all(chunk)
                session.flush()

            for chunk in chunked(data.outbox_events, batch_size):
                session.add_all(chunk)
                session.flush()

            session.commit()
        except Exception:
            session.rollback()
            raise

        stats.tenants_count = 0  # Tenant already existed
        stats.customers_count = len(data.customers)
        stats.products_count = len(data.products)
        stats.orders_count = len(data.orders)
        stats.order_items_count = len(data.order_items)
        stats.outbox_events_count = len(data.outbox_events)

        for order in data.orders:
            total_revenue += order.total_amount
            status_counts[order.status] = status_counts.get(order.status, 0) + 1

        for ev in data.outbox_events:
            if ev.processed_at is None:
                unprocessed_events += 1

        stats.total_revenue = total_revenue
        stats.status_counts = status_counts
        stats.unprocessed_outbox_count = unprocessed_events
        stats.insertion_seconds = time.perf_counter() - start_time
        return stats

    def insert_dataset_streaming(
        self,
        session: Session,
        base_time: Optional[datetime] = None,
        commit_per_tenant: Optional[bool] = None,
        prevent_duplicates: bool = True,
    ) -> GeneratorStats:
        """Insert dataset into database tenant-by-tenant for high-scale memory efficiency.

        Processes and flushes each tenant partition independently, keeping memory usage
        minimal regardless of total order or tenant volume.
        """
        if prevent_duplicates and self.config.existing_tenant_id is None:
            colliding = self.check_duplicate_prevention(session=session)
            if colliding:
                raise ValueError(
                    f"Accidental duplicate generation prevented: {len(colliding)} tenant domain(s) already exist: "
                    f"{colliding}. Specify --tenant-offset or use --incremental."
                )

        should_commit_per_tenant = (
            commit_per_tenant if commit_per_tenant is not None else self.config.commit_per_tenant
        )

        start_time = time.perf_counter()
        reference_time = base_time or self.config.get_reference_time()
        batch_size = self.config.batch_size

        stats = GeneratorStats()
        status_counts: Dict[str, int] = {}
        total_revenue = Decimal("0.00")
        unprocessed_events = 0

        try:
            for tenant_data in self.generate_tenant_stream(base_time=reference_time):
                session.add(tenant_data.tenant)
                session.flush()

                for chunk in chunked(tenant_data.customers, batch_size):
                    session.add_all(chunk)
                    session.flush()

                for chunk in chunked(tenant_data.products, batch_size):
                    session.add_all(chunk)
                    session.flush()

                for chunk in chunked(tenant_data.orders, batch_size):
                    session.add_all(chunk)
                    session.flush()

                for chunk in chunked(tenant_data.order_items, batch_size):
                    session.add_all(chunk)
                    session.flush()

                for chunk in chunked(tenant_data.outbox_events, batch_size):
                    session.add_all(chunk)
                    session.flush()

                stats.tenants_count += 1
                stats.customers_count += len(tenant_data.customers)
                stats.products_count += len(tenant_data.products)
                stats.orders_count += len(tenant_data.orders)
                stats.order_items_count += len(tenant_data.order_items)
                stats.outbox_events_count += len(tenant_data.outbox_events)

                for order in tenant_data.orders:
                    total_revenue += order.total_amount
                    status_counts[order.status] = status_counts.get(order.status, 0) + 1

                for ev in tenant_data.outbox_events:
                    if ev.processed_at is None:
                        unprocessed_events += 1

                if should_commit_per_tenant:
                    session.commit()
                    session.expunge_all()

            if not should_commit_per_tenant:
                session.commit()
        except Exception:
            session.rollback()
            raise

        stats.total_revenue = total_revenue
        stats.status_counts = status_counts
        stats.unprocessed_outbox_count = unprocessed_events
        stats.insertion_seconds = time.perf_counter() - start_time
        return stats

    def preview_cleanup_synthetic_data(
        self,
        session: Session,
        domain_pattern: Optional[str] = None,
    ) -> CleanupPlan:
        """Inspect and preview the records that would be removed by cleanup.

        Strictly enforces that the pattern targets the dedicated synthetic domain namespace.
        """
        pattern = domain_pattern or f"%.{self.config.domain_suffix}"

        # Guardrail: Never allow deletion outside the synthetic domain namespace
        if not ("synthetic" in pattern or pattern.endswith(".test")):
            raise ValueError(
                f"Safety Violation: Target pattern '{pattern}' is outside the dedicated synthetic "
                f"namespace (*.{SYNTHETIC_DOMAIN_SUFFIX}). Deletion of non-synthetic domains is forbidden."
            )

        # 1. Identify matching synthetic tenants
        tenant_stmt = select(Tenant.id).where(Tenant.domain.like(pattern))
        matching_ids = list(session.execute(tenant_stmt).scalars().all())

        if not matching_ids:
            return CleanupPlan(domain_pattern=pattern)

        # 2. Count associated child records belonging to these tenants
        customers_cnt = session.execute(
            select(func.count()).select_from(Customer).where(Customer.tenant_id.in_(matching_ids))
        ).scalar() or 0

        products_cnt = session.execute(
            select(func.count()).select_from(Product).where(Product.tenant_id.in_(matching_ids))
        ).scalar() or 0

        orders_cnt = session.execute(
            select(func.count()).select_from(Order).where(Order.tenant_id.in_(matching_ids))
        ).scalar() or 0

        order_items_cnt = session.execute(
            select(func.count()).select_from(OrderItem).where(OrderItem.tenant_id.in_(matching_ids))
        ).scalar() or 0

        outbox_cnt = session.execute(
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.tenant_id.in_(matching_ids))
        ).scalar() or 0

        return CleanupPlan(
            domain_pattern=pattern,
            tenant_ids=matching_ids,
            tenants_count=len(matching_ids),
            customers_count=customers_cnt,
            products_count=products_cnt,
            orders_count=orders_cnt,
            order_items_count=order_items_cnt,
            outbox_events_count=outbox_cnt,
        )

    def cleanup_synthetic_data(
        self,
        session: Session,
        domain_pattern: Optional[str] = None,
        confirm: bool = False,
    ) -> CleanupPlan:
        """Safely remove synthetic tenants and cascaded records with required confirmation.

        Safety Guardrails:
        1. Strictly restricted to domains within the dedicated synthetic namespace.
        2. Compiles a complete pre-deletion preview of all affected records.
        3. Requires explicit confirmation (confirm=True) before issuing any DELETE statement.

        Args:
            session: Active SQLAlchemy database session.
            domain_pattern: SQL LIKE pattern for synthetic domains.
            confirm: Boolean confirmation flag required to proceed with deletion.

        Returns:
            CleanupPlan with counts and execution status.
        """
        plan = self.preview_cleanup_synthetic_data(session=session, domain_pattern=domain_pattern)

        if plan.tenants_count == 0:
            return plan

        if not confirm:
            raise ValueError(
                f"Cleanup aborted: Explicit confirmation (confirm=True) is required to delete "
                f"{plan.tenants_count} synthetic tenants and {plan.total_records_count:,} total records."
            )

        try:
            # Purge synthetic tenants (PostgreSQL foreign keys automatically cascade to child tables)
            del_stmt = delete(Tenant).where(Tenant.id.in_(plan.tenant_ids))
            session.execute(del_stmt)
            session.commit()

            plan.confirmed = True
            plan.deleted = True
            return plan
        except Exception:
            session.rollback()
            raise
