"""User/admin services for message feedback."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_feedback_repo import MessageFeedbackRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.feedback import (
    AdminMessageFeedbackItem,
    AdminMessageFeedbackListResponse,
    AdminMessageFeedbackSummaryResponse,
    FeedbackEvidenceQuality,
    FeedbackRating,
    MessageFeedbackResponse,
    MessageFeedbackUpsertRequest,
)


class MessageFeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)
        self.feedback = MessageFeedbackRepository(session)

    async def upsert_feedback(
        self,
        *,
        user_id: UUID,
        message_id: UUID,
        request: MessageFeedbackUpsertRequest,
    ) -> MessageFeedbackResponse:
        message = await self.messages.get_by_id(message_id)
        if message is None:
            raise NotFoundError(error_code="MESSAGE_NOT_FOUND", message="Message not found")
        if message.role != "assistant":
            raise ValidationError(
                error_code="MESSAGE_FEEDBACK_TARGET_INVALID",
                message="Feedback can only be attached to assistant messages",
            )

        conversation = await self.conversations.get_by_user_and_id(user_id, message.conversation_id)
        if conversation is None:
            raise NotFoundError(error_code="MESSAGE_NOT_FOUND", message="Message not found")

        run_id = _metadata_uuid(message.metadata_json, "run_id")
        record = await self.feedback.upsert(
            user_id=user_id,
            conversation_id=message.conversation_id,
            message_id=message.id,
            run_id=run_id,
            rating=request.rating,
            evidence_quality=request.evidence_quality,
            hallucination_flag=request.hallucination_flag,
            comment=request.comment.strip() if request.comment else None,
            metadata_json={"source": "chat_message"},
        )
        await self.session.commit()
        return MessageFeedbackResponse.model_validate(record)

    async def get_feedback(self, *, user_id: UUID, message_id: UUID) -> MessageFeedbackResponse | None:
        message = await self.messages.get_by_id(message_id)
        if message is None:
            return None
        conversation = await self.conversations.get_by_user_and_id(user_id, message.conversation_id)
        if conversation is None:
            return None
        record = await self.feedback.get_by_user_and_message(user_id=user_id, message_id=message_id)
        return MessageFeedbackResponse.model_validate(record) if record else None

    async def list_feedback(
        self,
        *,
        page: int,
        page_size: int,
        rating: str | None = None,
        hallucination_flag: bool | None = None,
    ) -> AdminMessageFeedbackListResponse:
        rows, total = await self.feedback.list_feedback(
            page=page,
            page_size=page_size,
            rating=rating,
            hallucination_flag=hallucination_flag,
        )
        items = [
            AdminMessageFeedbackItem(
                id=record.id,
                user_id=record.user_id,
                user_phone=user.phone,
                conversation_id=record.conversation_id,
                message_id=record.message_id,
                run_id=record.run_id,
                rating=cast(FeedbackRating, record.rating),
                evidence_quality=cast(FeedbackEvidenceQuality | None, record.evidence_quality),
                hallucination_flag=record.hallucination_flag,
                comment=record.comment,
                message_preview=(message.content or "").strip()[:160],
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record, user, message in rows
        ]
        return AdminMessageFeedbackListResponse(items=items, total=total, page=page, page_size=page_size)

    async def summarize(self) -> AdminMessageFeedbackSummaryResponse:
        payload = await self.feedback.summarize()
        return AdminMessageFeedbackSummaryResponse(**payload)


def _metadata_uuid(metadata: dict[str, Any] | None, key: str) -> UUID | None:
    if not isinstance(metadata, dict):
        return None
    raw_value = metadata.get(key)
    if not isinstance(raw_value, str):
        return None
    try:
        return UUID(raw_value)
    except ValueError:
        return None
