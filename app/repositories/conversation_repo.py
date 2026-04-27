"""Repository helpers for conversation lifecycle operations."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


class ConversationRepository:
    """Data-access helpers for conversations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Conversation], int]:
        """List non-deleted conversations for one user with pagination."""
        base_query = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                ~Conversation.is_deleted,
            )
            .order_by(Conversation.updated_at.desc())
        )

        count_query = select(func.count()).select_from(base_query.subquery())
        total = int((await self.session.execute(count_query)).scalar_one())

        paginated_query = base_query.offset(skip).limit(limit)
        items = list((await self.session.execute(paginated_query)).scalars().all())
        return items, total

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        """Return one conversation by id, including soft-deleted rows."""
        result = await self.session.execute(select(Conversation).where(Conversation.id == conversation_id))
        return result.scalar_one_or_none()

    async def get_by_user_and_id(
        self,
        user_id: UUID,
        conversation_id: UUID,
    ) -> Conversation | None:
        """Return one non-deleted conversation owned by the given user."""
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                ~Conversation.is_deleted,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: UUID, title: str) -> Conversation:
        """Create and flush a new conversation row."""
        conversation = Conversation(user_id=user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        await self.session.refresh(conversation)
        return conversation

    async def update_title(self, conversation_id: UUID, new_title: str) -> Conversation | None:
        """Update the title of one conversation and return the fresh row."""
        result = await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=new_title)
            .returning(Conversation)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def soft_delete(self, conversation: Conversation) -> None:
        """Mark one conversation as soft deleted."""
        conversation.is_deleted = True
        await self.session.flush()

    async def restore(self, conversation_id: UUID) -> Conversation | None:
        """Restore one soft-deleted conversation."""
        result = await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(is_deleted=False)
            .returning(Conversation)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def touch(self, conversation_id: UUID) -> None:
        """Bump the updated_at timestamp for one conversation."""
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )
        await self.session.flush()

    async def hard_delete(self, conversation_id: UUID) -> bool:
        """Delete one conversation row permanently."""
        result = await self.session.execute(delete(Conversation).where(Conversation.id == conversation_id))
        await self.session.flush()
        rowcount = cast(CursorResult[Any], result).rowcount
        return int(rowcount or 0) > 0
