"""Repository helpers for message feedback."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.message_feedback import MessageFeedback
from app.models.user import User


class MessageFeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_and_message(self, *, user_id: UUID, message_id: UUID) -> MessageFeedback | None:
        stmt = select(MessageFeedback).where(
            MessageFeedback.user_id == user_id,
            MessageFeedback.message_id == message_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        run_id: UUID | None,
        rating: str,
        evidence_quality: str | None,
        hallucination_flag: bool,
        comment: str | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> MessageFeedback:
        feedback = await self.get_by_user_and_message(user_id=user_id, message_id=message_id)
        if feedback is None:
            feedback = MessageFeedback(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                run_id=run_id,
                rating=rating,
                evidence_quality=evidence_quality,
                hallucination_flag=hallucination_flag,
                comment=comment,
                metadata_json=metadata_json or {},
            )
            self.session.add(feedback)
        else:
            feedback.conversation_id = conversation_id
            feedback.run_id = run_id
            feedback.rating = rating
            feedback.evidence_quality = evidence_quality
            feedback.hallucination_flag = hallucination_flag
            feedback.comment = comment
            feedback.metadata_json = metadata_json or feedback.metadata_json or {}
        await self.session.flush()
        await self.session.refresh(feedback)
        return feedback

    async def list_feedback(
        self,
        *,
        page: int,
        page_size: int,
        rating: str | None = None,
        hallucination_flag: bool | None = None,
    ) -> tuple[list[tuple[MessageFeedback, User, Message]], int]:
        stmt = (
            select(MessageFeedback, User, Message)
            .join(User, User.id == MessageFeedback.user_id)
            .join(Message, Message.id == MessageFeedback.message_id)
        )
        count_stmt = select(func.count()).select_from(MessageFeedback)

        if rating:
            stmt = stmt.where(MessageFeedback.rating == rating)
            count_stmt = count_stmt.where(MessageFeedback.rating == rating)
        if hallucination_flag is not None:
            stmt = stmt.where(MessageFeedback.hallucination_flag.is_(hallucination_flag))
            count_stmt = count_stmt.where(MessageFeedback.hallucination_flag.is_(hallucination_flag))

        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = (
            stmt.order_by(MessageFeedback.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return [(row.MessageFeedback, row.User, row.Message) for row in result.all()], total

    async def summarize(self) -> dict[str, int]:
        stmt = select(
            func.count(MessageFeedback.id).label("total_feedback"),
            func.sum(case((MessageFeedback.rating == "helpful", 1), else_=0)).label("helpful_count"),
            func.sum(case((MessageFeedback.rating == "not_helpful", 1), else_=0)).label("not_helpful_count"),
            func.sum(case((MessageFeedback.hallucination_flag.is_(True), 1), else_=0)).label("hallucination_count"),
            func.sum(case((MessageFeedback.evidence_quality == "missing", 1), else_=0)).label("evidence_missing_count"),
            func.sum(case((MessageFeedback.evidence_quality == "insufficient", 1), else_=0)).label("evidence_insufficient_count"),
            func.sum(case((MessageFeedback.comment.is_not(None), 1), else_=0)).label("comment_count"),
        )
        row = (await self.session.execute(stmt)).one()
        return {
            "total_feedback": int(row.total_feedback or 0),
            "helpful_count": int(row.helpful_count or 0),
            "not_helpful_count": int(row.not_helpful_count or 0),
            "hallucination_count": int(row.hallucination_count or 0),
            "evidence_missing_count": int(row.evidence_missing_count or 0),
            "evidence_insufficient_count": int(row.evidence_insufficient_count or 0),
            "comment_count": int(row.comment_count or 0),
        }
