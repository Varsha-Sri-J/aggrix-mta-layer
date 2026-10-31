"""
AGGRIX MTA Layer - Core Application Configuration
Multi-Tenant Analytics & Aggregation Engine.
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    """
    # Application Metadata
    PROJECT_NAME: str = Field(default="AGGRIX MTA Layer", description="Application display name")
    VERSION: str = Field(default="0.1.0", description="Application version")
    DESCRIPTION: str = Field(
        default="Multi-Tenant Analytics & Aggregation Engine for Shopify-inspired e-commerce platforms",
        description="Application description"
    )
    ENVIRONMENT: str = Field(default="development", description="Runtime environment (development, staging, production)")
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    API_V1_STR: str = Field(default="/api/v1", description="API Version 1 routing prefix")

    # PostgreSQL Database Credentials
    POSTGRES_SERVER: str = Field(default="localhost", description="PostgreSQL host/service name")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_USER: str = Field(default="aggrix_user", description="PostgreSQL username")
    POSTGRES_PASSWORD: str = Field(default="aggrix_password", description="PostgreSQL password")
    POSTGRES_DB: str = Field(default="aggrix_db", description="PostgreSQL database name")

    # Direct database URL override
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Complete PostgreSQL connection string. When provided, takes precedence over discrete credentials."
    )

    # SQLAlchemy 2.0 Connection Pool Settings
    DB_POOL_SIZE: int = Field(default=10, description="Connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, description="Maximum overflow connections beyond pool size")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Seconds to wait before timing out on pool connection")
    DB_POOL_RECYCLE: int = Field(default=1800, description="Seconds after which connections are recycled")
    DB_ECHO: bool = Field(default=False, description="Log generated SQL queries to stdout")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def sqlalchemy_database_uri(self) -> str:
        """
        Constructs and returns the SQLAlchemy 2.0 connection URI.
        Normalizes postgres:// scheme to postgresql:// if needed.
        """
        if self.DATABASE_URL:
            uri = self.DATABASE_URL
            if uri.startswith("postgres://"):
                uri = uri.replace("postgres://", "postgresql://", 1)
            return uri

        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
