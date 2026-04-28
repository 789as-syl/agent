"""Admin user management and conversation audit service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import invalidate_user_cache
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.core.log_config import get_logger
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User, UserStatus
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository
from app.schemas.admin_users import (
    AdminAuditMessageResponse,
    AdminConversationSummaryResponse,
    AdminUserResponse,
)
from app.services.trace_projection import project_sse_event_dict

logger = get_logger(__name__)


def serialize_admin_user(user: User) -> AdminUserResponse:
    return AdminUserResponse.model_validate(user)


def serialize_admin_conversation(conversation: Conversation) -> AdminConversationSummaryResponse:
    return AdminConversationSummaryResponse.model_validate(conversation)


def serialize_admin_message(message: Message) -> AdminAuditMessageResponse:
    metadata = message.metadata_json or {}
    reply_to_message_id: UUID | None = None
    raw_reply_to = metadata.get("reply_to_message_id")
    if isinstance(raw_reply_to, str):
        try:
            reply_to_message_id = UUID(raw_reply_to)
        except ValueError:
            reply_to_message_id = None

    audit_playback = []
    raw_events = metadata.get("execution_trace") or metadata.get("audit_playback") or []
    if isinstance(raw_events, list):
        for index, raw_event in enumerate(raw_events[:50]):
            if not isinstance(raw_event, dict):
                continue
            event_json = {
                "event_id": str(raw_event.get("event_id") or f"{message.id}-trace-{index}"),
                "event_type": str(raw_event.get("event_type") or "execution_trace"),
                "step": int(raw_event.get("step") or index + 1),
                "timestamp": str(raw_event.get("timestamp") or message.created_at.isoformat()),
                "trace_data": raw_event.get("trace_data") if isinstance(raw_event.get("trace_data"), dict) else raw_event,
                "is_final": False,
            }
            projected = project_sse_event_dict(event_json)
            audit_playback.append(
                {
                    "id": projected["event_id"],
                    "kind": projected["kind"],
                    "title": projected["title"],
                    "status": projected["status"],
                    "timestamp": index,
                    "detail_sanitized": projected.get("detail_sanitized"),
                }
            )

    return AdminAuditMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at or datetime.now(UTC),
        reply_to_message_id=reply_to_message_id,
        content_blocks=message.content_blocks_json,
        audit_playback=audit_playback,
    )


class AdminUserService:
    """Business service for admin-only user and conversation audit flows."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
        status: UserStatus | None = None,
    ) -> tuple[list[User], int]:
        return await self.user_repo.list_admin_users(page=page, page_size=page_size, q=q, status=status)

    async def get_user(self, user_id: UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(error_code="USER_NOT_FOUND", message="用户不存在")
        return user

    async def update_user_status(
        self,
        *,
        target_user_id: UUID,
        actor_user: User,
        target_status: UserStatus,
        ban_reason: str | None = None,
    ) -> User:
        target_status = UserStatus(target_status)
        target_user = await self.get_user(target_user_id)

        if target_user.id == actor_user.id and target_status == UserStatus.DISABLED:
            raise AppError(
                error_code="INVALID_STATUS_TRANSITION",
                message="不能禁用当前管理员账号",
                status_code=403,
            )

        if target_user.status == target_status:
            return target_user

        normalized_reason = (ban_reason or "").strip() or None
        if target_status == UserStatus.DISABLED and not normalized_reason:
            raise ValidationError(
                error_code="BAN_REASON_REQUIRED",
                message="禁用用户时必须填写业务原因",
            )

        updated_user = await self.user_repo.update(
            target_user,
            status=target_status,
            status_changed_at=datetime.now(UTC),
            status_changed_by_user_id=actor_user.id,
            ban_reason=normalized_reason if target_status == UserStatus.DISABLED else None,
        )
        await invalidate_user_cache(updated_user.id)

        logger.info(
            "admin_user_status_updated",
            actor_user_id=str(actor_user.id),
            target_user_id=str(updated_user.id),
            target_status=target_status.value,
            has_ban_reason=bool(normalized_reason),
        )
        return updated_user

    async def list_user_conversations(
        self,
        *,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Conversation], int]:
        skip = max(0, (page - 1) * page_size)
        return await self.conversation_repo.list_by_user(user_id=user_id, skip=skip, limit=page_size)

    async def list_conversation_messages(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Message], int]:
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话不存在")
        if conversation.user_id != user_id:
            raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话不存在")
        skip = max(0, (page - 1) * page_size)
        return await self.message_repo.list_by_conversation(
            conversation_id=conversation_id,
            skip=skip,
            limit=page_size,
        )
