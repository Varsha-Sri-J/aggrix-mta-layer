"""
SQLAlchemy 2.0 Database Connection & Session Management
AGGRIX MTA Layer
"""

from typing import Any, Dict, Generator, Optional, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


# Base class for SQLAlchemy 2.0 declarative models (reserved for future schema models)
class Base(DeclarativeBase):
    pass


def _get_engine_kwargs() -> Dict[str, Any]:
    """
    Constructs engine configuration kwargs.
    Applies QueuePool connection pooling for PostgreSQL while avoiding
    unsupported parameters for other dialects (e.g. SQLite in test environments).
    """
    kwargs: Dict[str, Any] = {
        "pool_pre_ping": True,  # Test connection liveness prior to checkout
        "echo": settings.DB_ECHO,
    }

    uri = settings.sqlalchemy_database_uri
    if not uri.startswith("sqlite"):
        kwargs.update(
            {
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
                "pool_timeout": settings.DB_POOL_TIMEOUT,
                "pool_recycle": settings.DB_POOL_RECYCLE,
            }
        )

    return kwargs


# Configure SQLAlchemy 2.0 Engine
engine = create_engine(
    settings.sqlalchemy_database_uri,
    **_get_engine_kwargs(),
)

# Session factory for generating database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request
    and guarantees proper closure.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection(db: Optional[Session] = None) -> Tuple[bool, Optional[str]]:
    """
    Health check helper that executes 'SELECT 1' to verify PostgreSQL connectivity.
    Can be called with an existing session or will automatically manage its own session.

    Returns:
        Tuple[bool, Optional[str]]: (is_healthy, error_detail)
    """
    session_created = False
    if db is None:
        db = SessionLocal()
        session_created = True

    try:
        # SQLAlchemy 2.0 standard raw query execution
        result = db.execute(text("SELECT 1")).scalar()
        if result == 1:
            return True, None
        return False, f"Unexpected healthcheck query response: {result}"
    except Exception as exc:
        return False, str(exc)
    finally:
        if session_created:
            db.close()
