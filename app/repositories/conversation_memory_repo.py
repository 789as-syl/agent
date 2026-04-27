"""仓储模块：conversation_memory_repo。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_memory import ConversationMemory


class ConversationMemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_conversation_id(self, conversation_id: UUID) -> ConversationMemory | None:
        result = await self.session.execute(
            select(ConversationMemory).where(ConversationMemory.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def upsert_summary(
        self,
        conversation_id: UUID,
        summary_text: str,
        summary_version: int,
        last_message_id: UUID | None,
    ) -> ConversationMemory:
        existing = await self.get_by_conversation_id(conversation_id)
        if existing:
            existing.summary_text = summary_text
            existing.summary_version = summary_version
            existing.last_message_id = last_message_id
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        memory = ConversationMemory(
            conversation_id=conversation_id,
            summary_text=summary_text,
            summary_version=summary_version,
            last_message_id=last_message_id,
        )
        self.session.add(memory)
        await self.session.flush()
        await self.session.refresh(memory)
        return memory
