"""Pytest fixtures for AGGRIX database tests."""

import os
from collections.abc import Generator
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

# Ensure models are imported
import app.models  # noqa: F401
from app.core.config import settings
from app.database.base import Base
from app.database.connection import check_database_connection, create_database_engine


def is_postgres_available(url: str) -> bool:
    """Check if a live PostgreSQL instance is accepting connections."""
    try:
        test_engine = sa.create_engine(url, connect_args={"connect_timeout": 2})
        with test_engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        test_engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Return configured PostgreSQL URL or default test URL."""
    return os.getenv(
        "TEST_DATABASE_URL",
        os.getenv("DATABASE_URL", settings.sqlalchemy_database_uri),
    )


@pytest.fixture(scope="session")
def sqlite_engine() -> Generator[sa.Engine, None, None]:
    """In-memory SQLite engine configured with PRAGMA foreign_keys = ON.
    
    Provides rapid, fully isolated schema and constraint verification without
    requiring an external database service.
    """
    engine = sa.create_engine("sqlite:///:memory:")

    @sa.event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(sqlite_engine: sa.Engine) -> Generator[Session, None, None]:
    """Yield a database session within an isolated transaction.
    
    Transactions are rolled back after every test to keep tests completely independent.
    """
    connection = sqlite_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False)
    sess = session_factory()

    yield sess

    sess.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def postgres_session(postgres_url: str) -> Generator[Session, None, None]:
    """Yield a PostgreSQL session if a PostgreSQL instance is reachable.
    
    Skips cleanly with instructions if PostgreSQL is offline.
    """
    if not is_postgres_available(postgres_url):
        pytest.skip(
            f"PostgreSQL is not reachable at {postgres_url}. "
            "To run live PostgreSQL tests, start PostgreSQL (e.g. `docker compose up -d postgres`) "
            "and set TEST_DATABASE_URL."
        )

    engine = create_database_engine(url=postgres_url)
    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False)
    sess = session_factory()

    yield sess

    sess.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
    engine.dispose()

