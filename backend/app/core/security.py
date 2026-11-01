"""
AGGRIX Authentication & Cryptographic Security Module.

Provides:
- Secure password hashing and verification using bcrypt (with 12 salt rounds).
- Cryptographically verified JWT encoding and decoding using HMAC-SHA256.
- Strict token expiration and claim validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

import bcrypt
import jwt

from app.core.config import settings

# Precomputed 12-round bcrypt hash used for dummy password verification when an account is not found.
# Neutralizes username enumeration timing side-channels without introducing artificial latency.
DUMMY_PASSWORD_HASH = "$2b$12$e8rO27E.7f2uC8U5kX8m.OTwXNqE6hYJqQjF3kYmX2kP/y0vE1bWy"


def hash_password(plain_password: str) -> str:
    """
    Hashes a plaintext password using bcrypt with a generated salt (12 rounds).
    Never stores plaintext passwords.
    """
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored bcrypt hash.
    Constant-time comparison protects against timing attacks.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    subject: Union[str, uuid.UUID],
    role: str,
    tenant_id: Optional[Union[str, uuid.UUID]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generates a cryptographically signed HMAC-SHA256 JWT access token.
    Claims include:
    - sub: User UUID
    - role: UserRole (tenant_user, store_manager, platform_admin)
    - tenant_id: Associated tenant UUID (if tenant user)
    - iat: Issued at timestamp (UTC)
    - exp: Expiration timestamp (UTC)
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "role": str(role),
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and cryptographically verifies a JWT access token.
    Raises:
    - jwt.ExpiredSignatureError if token has expired.
    - jwt.InvalidTokenError if signature or payload is invalid.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "role", "exp", "iat"]},
    )
