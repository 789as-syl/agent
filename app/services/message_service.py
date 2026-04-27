"""Append-only message service helpers."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.message import Message
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository


class MessageService:
    """Coordinate message validation, moderation, and persistence."""

    ALLOWED_ROLES: ClassVar[frozenset[str]] = frozenset({"user", "assistant", "system"})
    BLOCKED_WORDS: ClassVar[frozenset[str]] = frozenset({"暴力", "色情", "违禁品"})

    def __init__(
        self,
        session: AsyncSession,
        conversation_repo: ConversationRepository | None = None,
    ) -> None:
        """Create a service bound to one database session."""
        self.session = session
        self.message_repo = MessageRepository(session)
        self.conversation_repo = conversation_repo

    async def list_messages(
        self,
        conversation_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Message], int]:
        """Return paginated messages for one conversation."""
        return await self.message_repo.list_by_conversation(
            conversation_id=conversation_id,
            skip=skip,
            limit=limit,
        )

    async def create_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: dict | None = None,
        enable_moderation: bool = True,
    ) -> Message:
        """Append one message and optionally bump the parent conversation timestamp."""
        if role not in self.ALLOWED_ROLES:
            raise ValidationError(
                error_code="MESSAGE_INVALID_ROLE",
                message=f"Invalid role: {role}. Allowed: {', '.join(sorted(self.ALLOWED_ROLES))}",
            )

        if enable_moderation:
            await self._moderate_content(content)

        message = await self.message_repo.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
        )

        if self.conversation_repo is not None:
            await self.conversation_repo.touch(conversation_id)

        return message

    async def _moderate_content(self, content: str) -> None:
        """Reject content that contains blocked keywords."""
        for word in self.BLOCKED_WORDS:
            if word in content:
                raise ValidationError(
                    error_code="MESSAGE_CONTENT_BLOCKED",
                    message=f"Content contains prohibited word: {word}",
                )
