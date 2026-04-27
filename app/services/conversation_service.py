"""服务模块：conversation_service。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.conversation import Conversation
from app.repositories.conversation_repo import ConversationRepository


class ConversationService:
    """Business service for conversation lifecycle."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.conversation_repo = ConversationRepository(session)

    async def list_conversations(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Conversation], int]:
        return await self.conversation_repo.list_by_user(user_id=user_id, skip=skip, limit=limit)

    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = await self.conversation_repo.get_by_user_and_id(user_id=user_id, conversation_id=conversation_id)
        if conversation:
            return conversation

        existing = await self.conversation_repo.get_by_id(conversation_id)
        if existing and existing.user_id != user_id:
            raise PermissionDeniedError(message="您无权访问此会话")
        raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话不存在")

    async def create_conversation(self, user_id: UUID, title: str) -> Conversation:
        if len(title) > 255:
            raise ValidationError(error_code="CONVERSATION_TITLE_TOO_LONG", message="标题长度不能超过 255 个字符")
        return await self.conversation_repo.create(user_id=user_id, title=title)

    async def update_title(self, user_id: UUID, conversation_id: UUID, new_title: str) -> Conversation:
        await self.get_conversation(user_id=user_id, conversation_id=conversation_id)
        if len(new_title) > 255:
            raise ValidationError(error_code="CONVERSATION_TITLE_TOO_LONG", message="标题长度不能超过 255 个字符")

        updated = await self.conversation_repo.update_title(conversation_id, new_title)
        if not updated:
            raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话不存在")
        return updated

    async def delete_conversation(self, user_id: UUID, conversation_id: UUID) -> None:
        conversation = await self.get_conversation(user_id=user_id, conversation_id=conversation_id)
        await self.conversation_repo.soft_delete(conversation)

    async def restore_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID,
        is_admin: bool = False,
    ) -> Conversation:
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话不存在")

        if not is_admin and conversation.user_id != user_id:
            raise PermissionDeniedError(message="您无权恢复此会话")

        if not conversation.is_deleted:
            return conversation

        restored = await self.conversation_repo.restore(conversation_id)
        if not restored:
            raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话恢复失败")
        return restored
