"""Password hashing and JWT token helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

TokenPayload = dict[str, Any]


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    salt = bcrypt.gensalt(rounds=settings.bcrypt_work_factor)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def _encode_token(payload: TokenPayload) -> str:
    return str(jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm))


def _build_token_payload(
    *,
    user_id: UUID,
    phone: str,
    token_type: str,
    expires_at: datetime,
    include_jti: bool,
) -> TokenPayload:
    payload: TokenPayload = {
        "sub": str(user_id),
        "phone": phone,
        "exp": expires_at,
        "type": token_type,
    }
    if include_jti:
        payload["jti"] = str(uuid4())
    return payload


def create_access_token(
    user_id: UUID,
    phone: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Create an access token and return the token with its TTL in seconds."""
    resolved_expires_delta = expires_delta or timedelta(minutes=settings.jwt_expiration_minutes)
    expire_at = datetime.now(UTC) + resolved_expires_delta
    payload = _build_token_payload(
        user_id=user_id,
        phone=phone,
        token_type="access",
        expires_at=expire_at,
        include_jti=False,
    )
    token = _encode_token(payload)
    return token, int(resolved_expires_delta.total_seconds())


async def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate an access token without blocking the event loop."""
    return await asyncio.to_thread(_decode_token_sync, token, "access")


def create_refresh_token(
    user_id: UUID,
    phone: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Create a refresh token and return the token with its TTL in seconds."""
    resolved_expires_delta = expires_delta or timedelta(days=settings.jwt_refresh_expiration_days)
    expire_at = datetime.now(UTC) + resolved_expires_delta
    payload = _build_token_payload(
        user_id=user_id,
        phone=phone,
        token_type="refresh",
        expires_at=expire_at,
        include_jti=True,
    )
    token = _encode_token(payload)
    return token, int(resolved_expires_delta.total_seconds())


async def decode_refresh_token(token: str) -> TokenPayload:
    """Decode and validate a refresh token without blocking the event loop."""
    return await asyncio.to_thread(_decode_token_sync, token, "refresh")


def _decode_token_sync(token: str, expected_type: str) -> TokenPayload:
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != expected_type:
        raise JWTError(f"Invalid token type: expected {expected_type}")
    return dict(payload)


def create_tokens_for_user(
    user_id: UUID,
    phone: str,
    access_expires_delta: timedelta | None = None,
    refresh_expires_delta: timedelta | None = None,
) -> dict[str, Any]:
    """Create a full access/refresh token pair for one user."""
    access_token, access_expires_in = create_access_token(user_id, phone, access_expires_delta)
    refresh_token, refresh_expires_in = create_refresh_token(user_id, phone, refresh_expires_delta)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_in": access_expires_in,
        "refresh_expires_in": refresh_expires_in,
        "token_type": "bearer",
    }
