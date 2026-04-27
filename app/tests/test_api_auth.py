"""Tests for auth API endpoints."""

import time

import pytest
from httpx import AsyncClient

from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
from app.services.token_service import TokenService


class TestAuthRegistration:
    """Tests for POST /api/v1/auth/register endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, mock_redis):
        """Test successful user registration."""
        import time
        timestamp_ms = int(time.time() * 1000)
        unique_part = str(timestamp_ms)[-8:]
        phone = f"139{unique_part}"

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "phone": phone,
                "password": "TestPass123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "access_expires_in" in data
        assert data["access_expires_in"] > 0

    @pytest.mark.asyncio
    async def test_register_invalid_phone_format(self, client: AsyncClient):
        """Test registration with invalid phone format."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "phone": "12345678901",
                "password": "TestPass123",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_register_invalid_password(self, client: AsyncClient):
        """Test registration with weak password."""
        phone = f"139{str(int(time.time() * 1000))[-8:]}"
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "phone": phone,
                "password": "weakpass",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_register_duplicate_phone(
        self,
        client: AsyncClient,
        test_user: User,
        mock_redis,
    ):
        """Test registration with already registered phone."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "phone": test_user.phone,
                "password": "TestPass123",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "USER_ALREADY_EXISTS"

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient):
        """Test registration with missing required fields."""
        response = await client.post(
            "/api/v1/auth/register",
            json={},
        )

        assert response.status_code == 422


class TestAuthLogin:
    """Tests for POST /api/v1/auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(
        self,
        client: AsyncClient,
        test_user: User,
        mock_redis,
    ):
        """Test successful login."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "phone": test_user.phone,
                "password": "TestPass123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "access_expires_in" in data

    @pytest.mark.asyncio
    async def test_login_invalid_phone(self, client: AsyncClient):
        """Test login with non-existent phone."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "phone": "13999999999",
                "password": "TestPass123",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "AUTH_INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test login with wrong password."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "phone": test_user.phone,
                "password": "WrongPassword123",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "AUTH_INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_disabled_account(
        self,
        client: AsyncClient,
        db_session,
        mock_redis,
    ):
        """Test login with disabled account."""
        from uuid import uuid4

        phone = f"139{str(int(time.time() * 1000))[-8:]}"
        user = User(
            id=uuid4(),
            phone=phone,
            password_hash=hash_password("TestPass123"),
            role=UserRole.USER,
            status=UserStatus.DISABLED,
        )
        db_session.add(user)
        await db_session.flush()

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "phone": phone,
                "password": "TestPass123",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "AUTH_ACCOUNT_DISABLED"


class TestAuthTokenRefresh:
    """Tests for POST /api/v1/auth/refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient, test_user: User, mock_redis):
        """Test successful token refresh."""
        tokens = TokenService.generate_tokens(
            user_id=str(test_user.id),
            phone=test_user.phone,
        )

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client: AsyncClient):
        """Test refresh with invalid token."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid_token"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self, client: AsyncClient):
        """Test refresh with expired token."""
        expired_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjE1MTYyMzkwMjJ9."
            "invalid"
        )

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": expired_token},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_disabled_user_rejected(
        self,
        client: AsyncClient,
        db_session,
        test_user: User,
    ):
        """Test refresh is rejected when the user has been disabled."""
        tokens = TokenService.generate_tokens(
            user_id=str(test_user.id),
            phone=test_user.phone,
        )
        test_user.status = UserStatus.DISABLED
        await db_session.flush()

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "账号已被禁用"


class TestAuthGetCurrentUser:
    """Tests for GET /api/v1/auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
    ):
        """Test getting current user info."""
        response = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["phone"] == test_user.phone
        assert data["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_me_no_token(self, client: AsyncClient):
        """Test getting current user without token."""
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_disabled_user_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session,
        test_user: User,
    ):
        """Test protected routes reject disabled users with an existing access token."""
        test_user.status = UserStatus.DISABLED
        await db_session.flush()

        response = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers,
        )

        assert response.status_code == 403
        data = response.json()
        assert data["error_code"] == "AUTH_ACCOUNT_DISABLED"


class TestAuthLogout:
    """Tests for POST /api/v1/auth/logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(
        self,
        client: AsyncClient,
        test_user: User,
        mock_redis,
    ):
        """Test successful logout."""
        tokens = TokenService.generate_tokens(
            user_id=str(test_user.id),
            phone=test_user.phone,
        )

        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_logout_without_token(self, client: AsyncClient):
        """Test logout without providing refresh token."""
        response = await client.post("/api/v1/auth/logout")

        assert response.status_code == 204
