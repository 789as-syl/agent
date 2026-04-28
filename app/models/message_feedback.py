"""User feedback on assistant messages."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MessageFeedback(Base, TimestampMixin):
    __tablename__ = "message_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_runs.id"), nullable=True)
    rating: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_message_feedback_user_message"),
        Index("ix_message_feedback_user_id", "user_id"),
        Index("ix_message_feedback_message_id", "message_id"),
        Index("ix_message_feedback_conversation_id", "conversation_id"),
        Index("ix_message_feedback_run_id", "run_id"),
        Index("ix_message_feedback_rating", "rating"),
        Index("ix_message_feedback_hallucination", "hallucination_flag"),
        Index("ix_message_feedback_created_at", "created_at"),
    )
