"""Base declarative class and metadata configuration."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Standardized constraint naming convention for PostgreSQL / Alembic migrations.
# This prevents auto-generated anonymous constraints which are difficult to alter or drop.
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Base model class for all AGGRIX entities."""

    metadata = metadata

    def __repr__(self) -> str:
        """Provide readable representation for debugging."""
        attrs = []
        for key in getattr(self, "__mapper__").column_attrs.keys():
            attrs.append(f"{key}={getattr(self, key)!r}")
        return f"<{self.__class__.__name__}({', '.join(attrs)})>"

