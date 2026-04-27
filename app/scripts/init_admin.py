"""脚本模块：init_admin。"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.models.engine import get_async_session_factory, init_db_engine
from app.models.user import User, UserRole, UserStatus


async def _create_admin(phone: str, password: str, reset_password: bool = False) -> None:
    init_db_engine()
    session_factory = get_async_session_factory()

    async with session_factory() as session:
        existing_by_phone = await session.execute(select(User).where(User.phone == phone))
        user = existing_by_phone.scalar_one_or_none()
        if user:
            if user.role != UserRole.ADMIN:
                user.role = UserRole.ADMIN
                user.status = UserStatus.ACTIVE
                user.password_hash = hash_password(password)
                session.add(user)
                await session.commit()
                print(f"Upgraded existing user {phone} to admin.")
                return
            if reset_password:
                user.password_hash = hash_password(password)
                user.status = UserStatus.ACTIVE
                session.add(user)
                await session.commit()
                print(f"Reset password for existing admin {phone}.")
                return
            print(f"User {phone} is already admin.")
            return

        admin_user = User(
            phone=phone,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        session.add(admin_user)
        await session.commit()
        print(f"Created admin user: {phone}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize first admin account")
    parser.add_argument("--phone", required=True, help="Admin phone number")
    parser.add_argument("--password", required=True, help="Admin password")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Reset password when the specified user already exists as admin",
    )
    args = parser.parse_args()

    asyncio.run(_create_admin(args.phone, args.password, reset_password=args.reset_password))


if __name__ == "__main__":
    main()
