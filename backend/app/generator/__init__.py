"""AGGRIX Synthetic E-commerce Data Generator package."""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

from app.generator.config import SYNTHETIC_DOMAIN_SUFFIX, GeneratorConfig
from app.generator.engine import (
    CleanupPlan,
    GeneratorDataset,
    GeneratorStats,
    SyntheticDataGenerator,
    TenantData,
)


def generate_synthetic_data(
    session: Session,
    config: Optional[GeneratorConfig] = None,
) -> GeneratorStats:
    """Convenience helper to generate and insert synthetic data into database."""
    generator = SyntheticDataGenerator(config=config)
    return generator.insert_dataset(session=session)


def preview_cleanup_synthetic_data(
    session: Session,
    config: Optional[GeneratorConfig] = None,
    domain_pattern: Optional[str] = None,
) -> CleanupPlan:
    """Convenience helper to preview synthetic data cleanup impact without deleting."""
    generator = SyntheticDataGenerator(config=config)
    return generator.preview_cleanup_synthetic_data(session=session, domain_pattern=domain_pattern)


def cleanup_synthetic_data(
    session: Session,
    config: Optional[GeneratorConfig] = None,
    domain_pattern: Optional[str] = None,
    confirm: bool = False,
) -> CleanupPlan:
    """Convenience helper to safely clean synthetic data with required confirmation."""
    generator = SyntheticDataGenerator(config=config)
    return generator.cleanup_synthetic_data(
        session=session,
        domain_pattern=domain_pattern,
        confirm=confirm,
    )


__all__ = [
    "SYNTHETIC_DOMAIN_SUFFIX",
    "CleanupPlan",
    "GeneratorConfig",
    "GeneratorDataset",
    "GeneratorStats",
    "SyntheticDataGenerator",
    "TenantData",
    "generate_synthetic_data",
    "preview_cleanup_synthetic_data",
    "cleanup_synthetic_data",
]
