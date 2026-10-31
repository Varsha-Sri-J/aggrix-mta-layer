"""
AGGRIX MTA Layer - Core Application Configuration
Multi-Tenant Analytics & Aggregation Engine.
"""

from typing import Any, List, Optional, Union
from pydantic import Field, field_validator
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

    # Analytics Aggregation Worker Configuration
    ANALYTICS_WORKER_POLL_INTERVAL_SECONDS: float = Field(
        default=1.0,
        description="Polling interval in seconds when outbox queue is empty"
    )
    ANALYTICS_WORKER_BATCH_SIZE: int = Field(
        default=100,
        description="Number of outbox events processed in a single batch"
    )
    ANALYTICS_WORKER_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum retry attempts before permanently dead-lettering a failing event"
    )
    ANALYTICS_WORKER_CONSUMER_NAME: str = Field(
        default="analytics_worker",
        description="Consumer identifier for tracking processed event receipts and dead letters"
    )

    # JWT Authentication & Cryptography Settings
    JWT_SECRET_KEY: str = Field(
        default="",
        description="Cryptographic secret key used for HMAC-SHA256 JWT signature verification (minimum 32 bytes, required)"
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Cryptographic algorithm for JWT encoding and decoding"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60,
        description="JWT access token validity duration in minutes"
    )

    # CORS Allowed Origins
    BACKEND_CORS_ORIGINS: Union[List[str], str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:8000",
        ],
        description="Explicit allowed CORS origins. Wildcard '*' is strictly forbidden."
    )


    @field_validator("JWT_SECRET_KEY", mode="after")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        """Enforces that JWT_SECRET_KEY is configured, >= 32 characters, and not an insecure default."""
        if not v or not v.strip():
            raise ValueError(
                "JWT_SECRET_KEY must be provided via environment configuration (.env or system environment). "
                "No default secret is permitted."
            )
        v = v.strip()
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters long for cryptographic security. Current length: {len(v)}"
            )
        insecure_placeholders = {
            "aggrix-super-secret-cryptographic-jwt-signing-key-32-bytes-min",
            "replace-with-a-secure-random-32-char-secret-for-local-dev-12345",
            "your-secret-key-must-be-at-least-32-characters-long",
            "secret",
            "changeme",
            "password",
            "default",
            "admin",
            "12345678901234567890123456789012",
        }
        lower_v = v.lower()
        if lower_v in insecure_placeholders or "placeholder" in lower_v or "super-secret-cryptographic" in lower_v:
            raise ValueError(
                "JWT_SECRET_KEY cannot use a known default, placeholder, or insecure secret string."
            )
        return v

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        """Parses and validates CORS origins, strictly rejecting the wildcard '*' origin."""
        if isinstance(v, str):
            origins = [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple, set)):
            origins = [str(i).strip() for i in v if str(i).strip()]
        else:
            origins = []

        for origin in origins:
            if origin == "*":
                raise ValueError("CORS wildcard '*' origin is strictly forbidden for security.")
        return origins

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
                uri = uri.replace("postgres://", "postgresql+psycopg2://", 1)
            elif uri.startswith("postgresql://") and not uri.startswith("postgresql+"):
                uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
            return uri

        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
