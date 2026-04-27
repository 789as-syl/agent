# ruff: noqa: B008
"""Shared API dependencies."""

from __future__ import annotations

import json
from contextlib import suppress
from enum import Enum
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.exceptions import ValidationError as AppValidationError
from app.core.redis import redis_client
from app.models.engine import get_async_session
from app.models.user import User, UserRole, UserStatus
from app.repositories.user_repo import UserRepository
from app.services.token_service import TokenService

security = HTTPBearer(auto_error=False)

USER_CACHE_PREFIX = "user:info:"
USER_CACHE_TTL = 1800


def build_user_cache_key(user_id: UUID | str) -> str:
    return f"{USER_CACHE_PREFIX}{user_id}"


async def invalidate_user_cache(user_id: UUID | str) -> None:
    with suppress(Exception):
        await redis_client.delete(build_user_cache_key(user_id))


def _serialize_user_to_dict(user: User) -> dict:
    role = user.role.value if isinstance(user.role, Enum) else str(user.role)
    status = user.status.value if isinstance(user.status, Enum) else str(user.status)
    return {
        "id": str(user.id),
        "phone": user.phone,
        "role": role,
        "status": status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _deserialize_dict_to_user(data: dict) -> User:
    return User(
        id=UUID(data["id"]),
        phone=data["phone"],
        role=UserRole(data["role"]),
        status=UserStatus(data["status"]),
    )


def _ensure_active_user(user: User) -> User:
    if user.status == UserStatus.DISABLED:
        raise AppError(
            error_code="AUTH_ACCOUNT_DISABLED",
            message="账号已被禁用",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_async_session),
    access_token_cookie: str | None = Cookie(default=None, alias="access_token"),
) -> User:
    _ = request
    auth_token = credentials.credentials if credentials else None
    auth_token = auth_token or access_token_cookie

    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = await TokenService.validate_token(auth_token)
        user_id_raw = payload.get("sub")
        if not user_id_raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            user_id = UUID(str(user_id_raw))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        cache_key = build_user_cache_key(user_id)
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            try:
                user_dict = json.loads(cached_data)
                return _ensure_active_user(_deserialize_dict_to_user(user_dict))
            except (json.JSONDecodeError, KeyError, ValueError):
                await redis_client.delete(cache_key)

        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        with suppress(Exception):
            await redis_client.setex(cache_key, USER_CACHE_TTL, json.dumps(_serialize_user_to_dict(user)))

        return _ensure_active_user(user)
    except (JWTError, AppValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise AppError(
            error_code="FORBIDDEN",
            message="Admin role required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return current_user
