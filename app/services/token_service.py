"""Authentication token service."""

from __future__ import annotations

import time
from uuid import UUID

from jose import ExpiredSignatureError, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.redis import redis_client
from app.core.security import (
    create_access_token,
    create_tokens_for_user,
    decode_access_token,
    decode_refresh_token,
)
from app.models.engine import get_async_session_factory
from app.models.user import UserStatus
from app.repositories.user_repo import UserRepository

REFRESH_TOKEN_BLACKLIST_PREFIX = "auth:blacklist:"


class TokenService:
    @staticmethod
    def generate_token(user_id: UUID, phone: str) -> tuple[str, int]:
        return create_access_token(user_id=user_id, phone=phone)

    @staticmethod
    def generate_tokens(user_id: UUID, phone: str) -> dict:
        return create_tokens_for_user(user_id=user_id, phone=phone)

    @staticmethod
    async def is_token_blacklisted(jti: str) -> bool:
        key = f"{REFRESH_TOKEN_BLACKLIST_PREFIX}{jti}"
        return bool(await redis_client.exists(key))

    @staticmethod
    async def blacklist_token(jti: str, expires_in: int) -> None:
        key = f"{REFRESH_TOKEN_BLACKLIST_PREFIX}{jti}"
        await redis_client.setex(key, expires_in, "1")

    @staticmethod
    async def validate_token(token: str) -> dict:
        try:
            return await decode_access_token(token)
        except ExpiredSignatureError as exc:
            raise ValidationError(message="令牌已过期", error_code="AUTH_TOKEN_EXPIRED") from exc
        except JWTError as exc:
            error_msg = str(exc)
            if "Invalid token type" in error_msg:
                raise ValidationError(message="无效的令牌类型", error_code="AUTH_INVALID_TOKEN_TYPE") from exc
            raise ValidationError(message="无效的令牌", error_code="AUTH_INVALID_TOKEN") from exc

    @staticmethod
    async def validate_refresh_token(token: str) -> dict:
        try:
            return await decode_refresh_token(token)
        except ExpiredSignatureError as exc:
            raise ValidationError(
                message="刷新令牌已过期，请重新登录",
                error_code="AUTH_REFRESH_TOKEN_EXPIRED",
            ) from exc
        except JWTError as exc:
            error_msg = str(exc)
            if "Invalid token type" in error_msg:
                raise ValidationError(
                    message="无效的令牌类型（应为 refresh）",
                    error_code="AUTH_INVALID_TOKEN_TYPE",
                ) from exc
            raise ValidationError(message="无效的刷新令牌", error_code="AUTH_INVALID_REFRESH_TOKEN") from exc

    @staticmethod
    async def refresh_access_token(refresh_token: str, session: AsyncSession | None = None) -> dict:
        payload = await TokenService.validate_refresh_token(refresh_token)

        jti = payload.get("jti")
        if jti and await TokenService.is_token_blacklisted(jti):
            raise ValidationError(
                message="刷新令牌已被撤销",
                error_code="AUTH_REFRESH_TOKEN_REVOKED",
            )

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValidationError(
                message="刷新令牌载荷不完整",
                error_code="AUTH_INVALID_TOKEN_PAYLOAD",
            )

        try:
            user_id = UUID(str(user_id_str))
        except ValueError as exc:
            raise ValidationError(
                message="刷新令牌中的用户标识无效",
                error_code="AUTH_INVALID_TOKEN_PAYLOAD",
            ) from exc

        owns_session = session is None
        if owns_session:
            session_factory = get_async_session_factory()
            session = session_factory()

        try:
            assert session is not None
            user = await UserRepository(session).get_by_id(user_id)
            if not user:
                raise ValidationError(
                    message="用户不存在",
                    error_code="AUTH_INVALID_TOKEN_PAYLOAD",
                )
            if user.status == UserStatus.DISABLED:
                raise ValidationError(
                    message="账号已被禁用",
                    error_code="AUTH_ACCOUNT_DISABLED",
                )

            if jti:
                exp = payload.get("exp", 0)
                remaining = max(int(exp - time.time()), 0)
                if remaining > 0:
                    await TokenService.blacklist_token(jti, remaining)

            new_tokens = create_tokens_for_user(user_id=user.id, phone=user.phone)
            return {
                "access_token": new_tokens["access_token"],
                "access_expires_in": new_tokens["access_expires_in"],
                "refresh_token": new_tokens["refresh_token"],
                "refresh_expires_in": new_tokens["refresh_expires_in"],
            }
        finally:
            if owns_session and session is not None:
                await session.close()

    @staticmethod
    async def extract_user_from_token(token: str) -> tuple[UUID, str]:
        payload = await TokenService.validate_token(token)
        user_id_str = payload.get("sub")
        phone = payload.get("phone")

        if not user_id_str or not phone:
            raise ValidationError(
                message="令牌载荷不完整",
                error_code="AUTH_INVALID_TOKEN_PAYLOAD",
            )

        try:
            user_id = UUID(str(user_id_str))
        except ValueError as exc:
            raise ValidationError(
                message="令牌中的用户标识无效",
                error_code="AUTH_INVALID_TOKEN_PAYLOAD",
            ) from exc

        return user_id, phone
