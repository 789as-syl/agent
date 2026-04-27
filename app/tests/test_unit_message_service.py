"""Regression tests for message service validation and persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.services.message_service import MessageService


async def _create_conversation(
    session: AsyncSession,
    user: User,
    title: str = "Message Test",
) -> Conversation:
    conversation = Conversation(
        id=uuid4(),
        user_id=user.id,
        title=title,
        is_deleted=False,
    )
    session.add(conversation)
    await session.flush()
    return conversation


class TestMessageService:
    @pytest.mark.asyncio
    async def test_create_message_persists_message_and_touches_conversation(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conversation = await _create_conversation(db_session, test_user)
        conversation_repo = ConversationRepository(db_session)

        with patch.object(conversation_repo, "touch", AsyncMock()) as touch_mock:
            service = MessageService(db_session, conversation_repo=conversation_repo)
            message = await service.create_message(
                conversation_id=conversation.id,
                role="user",
                content="hello",
                metadata={"source": "test"},
            )

        persisted_messages = await MessageRepository(db_session).list_all_by_conversation(conversation.id)

        assert isinstance(message, Message)
        assert message.conversation_id == conversation.id
        assert message.role == "user"
        assert message.content == "hello"
        assert message.metadata_json == {"source": "test"}
        assert len(persisted_messages) == 1
        touch_mock.assert_awaited_once_with(conversation.id)

    @pytest.mark.asyncio
    async def test_create_message_rejects_invalid_role(self, db_session: AsyncSession) -> None:
        service = MessageService(db_session)

        with pytest.raises(ValidationError) as exc_info:
            await service.create_message(
                conversation_id=uuid4(),
                role="tool",
                content="hello",
            )

        assert exc_info.value.error_code == "MESSAGE_INVALID_ROLE"

    @pytest.mark.asyncio
    async def test_create_message_blocks_sensitive_content_by_default(self, db_session: AsyncSession) -> None:
        service = MessageService(db_session)

        with pytest.raises(ValidationError) as exc_info:
            await service.create_message(
                conversation_id=uuid4(),
                role="user",
                content="这里包含暴力内容",
            )

        assert exc_info.value.error_code == "MESSAGE_CONTENT_BLOCKED"

    @pytest.mark.asyncio
    async def test_create_message_can_skip_moderation(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conversation = await _create_conversation(db_session, test_user, title="No moderation")
        service = MessageService(db_session)

        message = await service.create_message(
            conversation_id=conversation.id,
            role="assistant",
            content="这里包含暴力内容",
            enable_moderation=False,
        )

        assert message.role == "assistant"
        assert message.content == "这里包含暴力内容"
