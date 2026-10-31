"""Configuration for AGGRIX Synthetic E-commerce Data Generator.

Provides strongly typed settings controlling record volumes, distributions,
random seed, and batching parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

# Dedicated namespace strictly reserved for generated synthetic data
SYNTHETIC_DOMAIN_SUFFIX: str = "synthetic.aggrix.test"


@dataclass
class GeneratorConfig:
    """Configuration parameters for synthetic data generation."""

    # Volume parameters
    tenants_count: int = 5
    customers_per_tenant: int = 500
    products_per_tenant: int = 100
    orders_per_tenant: int = 2000

    # Batching and performance
    batch_size: int = 1000

    # Determinism and time horizon
    seed: int = 42
    days_history: int = 60
    as_of: Optional[datetime] = None  # Configurable reference timestamp for reproducible datasets

    # Event publishing parameters
    unprocessed_outbox_percentage: float = 0.10  # 10% left with processed_at = None

    # Order status weights
    status_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "fulfilled": 0.65,
            "paid": 0.20,
            "pending": 0.10,
            "cancelled": 0.05,
        }
    )

    # Order item sizing
    min_items_per_order: int = 1
    max_items_per_order: int = 5
    min_item_quantity: int = 1
    max_item_quantity: int = 3

    # Currency and store domain suffix
    currency: str = "USD"
    domain_suffix: str = SYNTHETIC_DOMAIN_SUFFIX

    def get_reference_time(self) -> datetime:
        """Return the effective reference timestamp, normalized to UTC."""
        if self.as_of is not None:
            if self.as_of.tzinfo is None:
                return self.as_of.replace(tzinfo=timezone.utc)
            return self.as_of.astimezone(timezone.utc)
        return datetime.now(timezone.utc)

    def validate(self) -> None:
        """Validate configuration bounds and invariants."""
        if self.tenants_count <= 0:
            raise ValueError("tenants_count must be > 0")
        if self.customers_per_tenant <= 0:
            raise ValueError("customers_per_tenant must be > 0")
        if self.products_per_tenant <= 0:
            raise ValueError("products_per_tenant must be > 0")
        if self.orders_per_tenant < 0:
            raise ValueError("orders_per_tenant must be >= 0")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if self.days_history <= 0:
            raise ValueError("days_history must be > 0")
        if not 0.0 <= self.unprocessed_outbox_percentage <= 1.0:
            raise ValueError("unprocessed_outbox_percentage must be between 0.0 and 1.0")
        if self.min_items_per_order <= 0:
            raise ValueError("min_items_per_order must be > 0")
        if self.max_items_per_order < self.min_items_per_order:
            raise ValueError("max_items_per_order must be >= min_items_per_order")
        if self.min_item_quantity <= 0:
            raise ValueError("min_item_quantity must be > 0")
        if self.max_item_quantity < self.min_item_quantity:
            raise ValueError("max_item_quantity must be >= min_item_quantity")
        if not ("synthetic" in self.domain_suffix or self.domain_suffix.endswith(".test")):
            raise ValueError(
                f"domain_suffix must belong to a dedicated synthetic namespace "
                f"(e.g. '{SYNTHETIC_DOMAIN_SUFFIX}'). Got: '{self.domain_suffix}'"
            )
