"""Unit tests for admin user service."""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError, ValidationError
from app.models.user import UserStatus
from app.services.admin_user_service import AdminUserService


class TestAdminUserService:
    @pytest.mark.asyncio
    async def test_list_users_supports_uuid_search(self, db_session, test_user, other_user):
        service = AdminUserService(db_session)

        items, total = await service.list_users(q=str(test_user.id))

        assert total == 1
        assert [item.id for item in items] == [test_user.id]
        assert other_user.id not in {item.id for item in items}

    @pytest.mark.asyncio
    async def test_list_users_supports_phone_search_and_status_filter(self, db_session, test_user, other_user):
        other_user.status = UserStatus.DISABLED
        await db_session.flush()
        service = AdminUserService(db_session)

        phone_fragment = other_user.phone[-4:]
        items, total = await service.list_users(q=phone_fragment, status=UserStatus.DISABLED)

        assert total == 1
        assert [item.id for item in items] == [other_user.id]
        assert test_user.id not in {item.id for item in items}

    @pytest.mark.asyncio
    async def test_disable_user_sets_snapshot_and_invalidates_cache(
        self,
        db_session,
        test_user,
        test_admin_user,
        patch_runtime_redis,
    ):
        service = AdminUserService(db_session)

        updated_user = await service.update_user_status(
            target_user_id=test_user.id,
            actor_user=test_admin_user,
            target_status=UserStatus.DISABLED,
            ban_reason="涉嫌违规问答",
        )

        assert updated_user.status == UserStatus.DISABLED
        assert updated_user.ban_reason == "涉嫌违规问答"
        assert updated_user.status_changed_at is not None
        assert updated_user.status_changed_by_user_id == test_admin_user.id
        patch_runtime_redis.delete.assert_awaited_once_with(f"user:info:{test_user.id}")

    @pytest.mark.asyncio
    async def test_enable_user_clears_reason(self, db_session, test_user, test_admin_user, patch_runtime_redis):
        service = AdminUserService(db_session)
        await service.update_user_status(
            target_user_id=test_user.id,
            actor_user=test_admin_user,
            target_status=UserStatus.DISABLED,
            ban_reason="首次禁用",
        )
        patch_runtime_redis.delete.reset_mock()

        updated_user = await service.update_user_status(
            target_user_id=test_user.id,
            actor_user=test_admin_user,
            target_status=UserStatus.ACTIVE,
        )

        assert updated_user.status == UserStatus.ACTIVE
        assert updated_user.ban_reason is None
        assert updated_user.status_changed_by_user_id == test_admin_user.id
        patch_runtime_redis.delete.assert_awaited_once_with(f"user:info:{test_user.id}")

    @pytest.mark.asyncio
    async def test_same_state_update_is_idempotent(self, db_session, test_user, test_admin_user, patch_runtime_redis):
        service = AdminUserService(db_session)
        first_update = await service.update_user_status(
            target_user_id=test_user.id,
            actor_user=test_admin_user,
            target_status=UserStatus.DISABLED,
            ban_reason="首次禁用",
        )
        snapshot = (
            first_update.status_changed_at,
            first_update.status_changed_by_user_id,
            first_update.ban_reason,
        )
        patch_runtime_redis.delete.reset_mock()

        second_update = await service.update_user_status(
            target_user_id=test_user.id,
            actor_user=test_admin_user,
            target_status=UserStatus.DISABLED,
            ban_reason="尝试修改原因",
        )

        assert (
            second_update.status_changed_at,
            second_update.status_changed_by_user_id,
            second_update.ban_reason,
        ) == snapshot
        patch_runtime_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disable_requires_reason(self, db_session, test_user, test_admin_user):
        service = AdminUserService(db_session)

        with pytest.raises(ValidationError) as exc_info:
            await service.update_user_status(
                target_user_id=test_user.id,
                actor_user=test_admin_user,
                target_status=UserStatus.DISABLED,
                ban_reason="   ",
            )

        assert exc_info.value.error_code == "BAN_REASON_REQUIRED"

    @pytest.mark.asyncio
    async def test_self_disable_is_rejected(self, db_session, test_admin_user):
        service = AdminUserService(db_session)

        with pytest.raises(AppError) as exc_info:
            await service.update_user_status(
                target_user_id=test_admin_user.id,
                actor_user=test_admin_user,
                target_status=UserStatus.DISABLED,
                ban_reason="误操作",
            )

        assert exc_info.value.error_code == "INVALID_STATUS_TRANSITION"
        assert exc_info.value.status_code == 403
