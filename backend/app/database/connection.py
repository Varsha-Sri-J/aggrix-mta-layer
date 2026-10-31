"""
SQLAlchemy 2.0 Database Connection & Session Management
AGGRIX MTA Layer
Unified canonical database connection module preserving both FastAPI dependency
and standalone context manager / migration capabilities.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.database.base import Base, metadata


def create_database_engine(
    url: Optional[str] = None,
    **kwargs: Any,
) -> Engine:
    """
    Constructs a configured SQLAlchemy 2.0 Engine.
    Applies QueuePool connection pooling for PostgreSQL while avoiding
    unsupported parameters for other dialects (e.g. SQLite in test environments).

    Args:
        url: Optional explicit database URL overriding application settings.
        **kwargs: Additional parameters passed to create_engine.
    """
    target_url = url or settings.sqlalchemy_database_uri
    is_sqlite = target_url.startswith("sqlite")

    engine_kwargs: Dict[str, Any] = {
        "echo": kwargs.pop("echo", settings.DB_ECHO),
    }

    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": kwargs.pop("pool_size", settings.DB_POOL_SIZE),
                "max_overflow": kwargs.pop("max_overflow", settings.DB_MAX_OVERFLOW),
                "pool_timeout": kwargs.pop("pool_timeout", settings.DB_POOL_TIMEOUT),
                "pool_recycle": kwargs.pop("pool_recycle", settings.DB_POOL_RECYCLE),
                "pool_pre_ping": kwargs.pop("pool_pre_ping", True),
            }
        )

    engine_kwargs.update(kwargs)
    return create_engine(target_url, **engine_kwargs)


# Canonical default application engine and session factory
engine = create_database_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Essential for FastAPI attribute access after commit
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


@contextmanager
def get_db_session(
    custom_session_factory: Optional[sessionmaker[Session]] = None,
) -> Generator[Session, None, None]:
    """
    Context manager for standalone scripts, migrations, and test helpers.
    Automatically commits on normal completion or rolls back upon unhandled exception.
    """
    factory = custom_session_factory or SessionLocal
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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
        result = db.execute(text("SELECT 1")).scalar()
        if result == 1:
            return True, None
        return False, f"Unexpected healthcheck query response: {result}"
    except Exception as exc:
        return False, str(exc)
    finally:
        if session_created:
            db.close()


def check_database_connection(target_engine: Optional[Engine] = None) -> bool:
    """
    Perform a quick boolean healthcheck against the database engine.
    Used by test fixtures and startup probes.
    """
    eng = target_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
