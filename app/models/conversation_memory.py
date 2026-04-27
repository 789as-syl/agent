"""数据模型模块：conversation_memory。"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ConversationMemory(Base, TimestampMixin):
    __tablename__ = "conversation_memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_conversation_memories_conversation_id"),
        Index("ix_conversation_memories_conversation_id", "conversation_id"),
    )
