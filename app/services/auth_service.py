"""服务模块：auth_service。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.log_config import get_logger
from app.core.security import hash_password, verify_password
from app.models.user import User, UserStatus
from app.repositories.user_repo import UserRepository

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def register(self, phone: str, password: str) -> User:
        existing_user = await self.user_repo.get_by_phone(phone)
        if existing_user:
            raise ValidationError(
                error_code="USER_ALREADY_EXISTS",
                message="手机号已被注册",
            )

        password_hash = hash_password(password)
        return await self.user_repo.create(phone=phone, password_hash=password_hash)

    async def authenticate(self, phone: str, password: str) -> User:
        user = await self.user_repo.get_by_phone(phone)
        if not user:
            logger.warning("Authentication failed: user not found", phone=phone)
            raise ValidationError(
                error_code="AUTH_INVALID_CREDENTIALS",
                message="手机号或密码错误",
            )

        if not verify_password(password, user.password_hash):
            logger.warning("Authentication failed: password mismatch", user_id=str(user.id), phone=phone)
            raise ValidationError(
                error_code="AUTH_INVALID_CREDENTIALS",
                message="手机号或密码错误",
            )

        if user.status == UserStatus.DISABLED:
            logger.warning("Authentication failed: account disabled", user_id=str(user.id), phone=phone)
            raise ValidationError(
                error_code="AUTH_ACCOUNT_DISABLED",
                message="账号已被禁用",
            )

        return user

    async def get_user_by_id(self, user_id: UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(
                error_code="USER_NOT_FOUND",
                message="用户不存在",
            )
        return user
