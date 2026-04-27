"""User repository."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.user import User, UserRole, UserStatus


class UserRepository:
    """Data access wrapper for ``users``."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone == phone)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_list(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        role: UserRole | None = None,
        status: UserStatus | None = None,
    ) -> tuple[list[User], int]:
        count_stmt = select(func.count()).select_from(User)
        list_stmt = select(User)

        filters = []
        if role is not None:
            filters.append(User.role == role)
        if status is not None:
            filters.append(User.status == status)

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        list_stmt = list_stmt.offset(skip).limit(limit).order_by(User.created_at.desc())

        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        list_result = await self.session.execute(list_stmt)
        users = list(list_result.scalars().all())
        return users, total

    async def list_admin_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
        status: UserStatus | None = None,
    ) -> tuple[list[User], int]:
        offset = max(page - 1, 0) * page_size
        count_stmt = select(func.count()).select_from(User)
        list_stmt = select(User)

        filters = []
        if status is not None:
            filters.append(User.status == status)

        normalized_q = (q or "").strip()
        if normalized_q:
            try:
                filters.append(User.id == UUID(normalized_q))
            except ValueError:
                filters.append(User.phone.contains(normalized_q))

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        list_stmt = list_stmt.order_by(User.created_at.desc()).offset(offset).limit(page_size)

        total = (await self.session.execute(count_stmt)).scalar_one()
        items = list((await self.session.execute(list_stmt)).scalars().all())
        return items, total

    async def create(self, phone: str, password_hash: str) -> User:
        user = User(phone=phone, password_hash=password_hash)
        self.session.add(user)

        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            if "unique constraint" in str(exc.orig).lower() or "duplicate key" in str(exc.orig).lower():
                raise ConflictError(
                    message="手机号已被注册",
                    details={"phone": phone},
                    error_code="USER_PHONE_CONFLICT",
                ) from exc
            raise

        await self.session.refresh(user)
        return user

    async def update(self, user: User, **kwargs: Any) -> User:
        valid_columns = {column.name for column in User.__table__.columns}
        update_data = {key: value for key, value in kwargs.items() if key in valid_columns}
        if not update_data:
            return user

        stmt = update(User).where(User.id == user.id).values(**update_data)
        await self.session.execute(stmt)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def update_status(self, user: User, status: UserStatus) -> User:
        return await self.update(user, status=status)

    async def update_role(self, user: User, role: UserRole) -> User:
        return await self.update(user, role=role)

    async def soft_delete(self, user: User) -> User:
        return await self.update_status(user, UserStatus.DISABLED)

    async def hard_delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.flush()
