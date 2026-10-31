"""Database engine, configuration, and session factory management."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


class DatabaseSettings(BaseSettings):
    """Database connection and pooling settings read from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/aggrix",
        description="PostgreSQL connection string.",
    )
    DB_POOL_SIZE: int = Field(default=10, description="Database connection pool size.")
    DB_MAX_OVERFLOW: int = Field(
        default=20,
        description="Max overflow connections allowed above pool size.",
    )
    DB_POOL_TIMEOUT: int = Field(
        default=30,
        description="Seconds to wait before giving up on obtaining a connection.",
    )
    DB_POOL_RECYCLE: int = Field(
        default=1800,
        description="Seconds after which connections are recycled (30 minutes).",
    )
    DB_POOL_PRE_PING: bool = Field(
        default=True,
        description="Test connections for liveliness upon checkout.",
    )
    DB_ECHO: bool = Field(
        default=False,
        description="If True, log all SQL statements emitted by SQLAlchemy.",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: Any) -> str:
        """Normalize URL scheme (e.g. Heroku postgres:// to postgresql+psycopg2://)."""
        if isinstance(v, str):
            val = v.strip()
            if val.startswith("postgres://"):
                return "postgresql+psycopg2://" + val[len("postgres://") :]
            if val.startswith("postgresql://") and not val.startswith("postgresql+"):
                return "postgresql+psycopg2://" + val[len("postgresql://") :]
            return val
        return str(v)

    @property
    def sanitized_url(self) -> str:
        """Return DATABASE_URL with password masked for safe logging/inspection."""
        url = self.DATABASE_URL
        if "@" in url and "://" in url:
            scheme, rest = url.split("://", 1)
            user_info, host_info = rest.split("@", 1)
            if ":" in user_info:
                username, _ = user_info.split(":", 1)
                return f"{scheme}://{username}:***@{host_info}"
        return url


def get_database_settings() -> DatabaseSettings:
    """Instantiate and return settings loaded from environment."""
    return DatabaseSettings()


def create_database_engine(
    url: str | None = None,
    settings: DatabaseSettings | None = None,
    **kwargs: Any,
) -> Engine:
    """Create a configured SQLAlchemy Engine.
    
    Args:
        url: Optional explicit database URL overriding settings.
        settings: Optional DatabaseSettings instance.
        **kwargs: Additional parameters passed to create_engine.
    """
    cfg = settings or get_database_settings()
    target_url = url or cfg.DATABASE_URL

    # Pool arguments only apply to non-SQLite / pooled engines
    is_sqlite = target_url.startswith("sqlite")
    engine_kwargs: dict[str, Any] = {
        "echo": kwargs.pop("echo", cfg.DB_ECHO),
    }

    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": kwargs.pop("pool_size", cfg.DB_POOL_SIZE),
                "max_overflow": kwargs.pop("max_overflow", cfg.DB_MAX_OVERFLOW),
                "pool_timeout": kwargs.pop("pool_timeout", cfg.DB_POOL_TIMEOUT),
                "pool_recycle": kwargs.pop("pool_recycle", cfg.DB_POOL_RECYCLE),
                "pool_pre_ping": kwargs.pop("pool_pre_ping", cfg.DB_POOL_PRE_PING),
            }
        )

    engine_kwargs.update(kwargs)
    return create_engine(target_url, **engine_kwargs)


# Default application engine and session factory
settings = get_database_settings()
engine = create_database_engine(settings=settings)
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions per request.
    
    Usage in FastAPI routes:
        @app.get("/tenants")
        def list_tenants(db: Session = Depends(get_db)):
            ...
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_db_session(
    custom_session_factory: sessionmaker[Session] | None = None,
) -> Generator[Session, None, None]:
    """Context manager for standalone scripts, migrations, and test helpers.
    
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


def check_database_connection(target_engine: Engine | None = None) -> bool:
    """Perform a quick healthcheck against the database."""
    eng = target_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

