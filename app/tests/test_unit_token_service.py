"""Tests for token service."""

import base64
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.user import User, UserStatus
from app.services.token_service import TokenService


class TestTokenGeneration:
    def test_generate_access_token_success(self) -> None:
        user_id = uuid4()
        tokens = TokenService.generate_tokens(
            user_id=user_id,
            phone="13800138000",
        )

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["access_expires_in"] > 0
        assert tokens["refresh_expires_in"] > 0

    def test_generate_tokens_contains_user_info(self) -> None:
        user_id = uuid4()
        tokens = TokenService.generate_tokens(
            user_id=user_id,
            phone="13800138000",
        )

        parts = tokens["access_token"].split(".")
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))

        assert payload["sub"] == str(user_id)
        assert payload["phone"] == "13800138000"

    def test_generate_tokens_with_different_users(self) -> None:
        user_id1 = uuid4()
        user_id2 = uuid4()
        tokens1 = TokenService.generate_tokens(
            user_id=user_id1,
            phone="13800138001",
        )
        tokens2 = TokenService.generate_tokens(
            user_id=user_id2,
            phone="13800138002",
        )

        assert tokens1["access_token"] != tokens2["access_token"]


class TestTokenValidation:
    @pytest.mark.asyncio
    async def test_validate_access_token_success(self) -> None:
        user_id = uuid4()
        tokens = TokenService.generate_tokens(
            user_id=user_id,
            phone="13800138000",
        )

        payload = await TokenService.validate_token(tokens["access_token"])

        assert payload["sub"] == str(user_id)
        assert payload["phone"] == "13800138000"
        assert payload["type"] == "access"

    @pytest.mark.asyncio
    async def test_validate_refresh_token_success(self) -> None:
        user_id = uuid4()
        tokens = TokenService.generate_tokens(
            user_id=user_id,
            phone="13800138000",
        )

        payload = await TokenService.validate_refresh_token(tokens["refresh_token"])

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"

    @pytest.mark.asyncio
    async def test_validate_invalid_token(self) -> None:
        with pytest.raises(ValidationError):
            await TokenService.validate_token("invalid_token")


class TestTokenBlacklist:
    @pytest.mark.asyncio
    async def test_blacklist_token_success(self) -> None:
        with patch("app.services.token_service.redis_client") as mock_redis:
            mock_redis.setex = AsyncMock(return_value=True)

            jti = "test-jti"
            expires_in = 3600

            await TokenService.blacklist_token(jti, expires_in)

            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_true(self) -> None:
        with patch("app.services.token_service.redis_client") as mock_redis:
            mock_redis.exists = AsyncMock(return_value=1)

            result = await TokenService.is_token_blacklisted("test-jti")

            assert result is True

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_false(self) -> None:
        with patch("app.services.token_service.redis_client") as mock_redis:
            mock_redis.exists = AsyncMock(return_value=0)

            result = await TokenService.is_token_blacklisted("test-jti")

            assert result is False


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_access_token_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        tokens = TokenService.generate_tokens(
            user_id=test_user.id,
            phone=test_user.phone,
        )

        with patch("app.services.token_service.redis_client") as mock_redis:
            mock_redis.exists = AsyncMock(return_value=0)
            mock_redis.setex = AsyncMock(return_value=True)

            new_tokens = await TokenService.refresh_access_token(
                tokens["refresh_token"],
                session=db_session,
            )

            assert "access_token" in new_tokens
            assert "refresh_token" in new_tokens

    @pytest.mark.asyncio
    async def test_refresh_with_blacklisted_token(self) -> None:
        user_id = uuid4()
        tokens = TokenService.generate_tokens(
            user_id=user_id,
            phone="13800138000",
        )

        with patch("app.services.token_service.redis_client") as mock_redis:
            mock_redis.exists = AsyncMock(return_value=1)

            with pytest.raises(ValidationError):
                await TokenService.refresh_access_token(tokens["refresh_token"])

    @pytest.mark.asyncio
    async def test_refresh_disabled_user_rejected(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        test_user.status = UserStatus.DISABLED
        await db_session.flush()

        tokens = TokenService.generate_tokens(
            user_id=test_user.id,
            phone=test_user.phone,
        )

        with patch("app.services.token_service.redis_client") as mock_redis:
            mock_redis.exists = AsyncMock(return_value=0)
            mock_redis.setex = AsyncMock(return_value=True)

            with pytest.raises(ValidationError) as exc_info:
                await TokenService.refresh_access_token(
                    tokens["refresh_token"],
                    session=db_session,
                )

        assert exc_info.value.error_code == "AUTH_ACCOUNT_DISABLED"
