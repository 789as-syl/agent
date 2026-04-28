# ruff: noqa: B008
"""User message feedback API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_user
from app.models.user import User
from app.schemas.feedback import MessageFeedbackResponse, MessageFeedbackUpsertRequest
from app.services.message_feedback_service import MessageFeedbackService

message_feedback_router = APIRouter(prefix="/api/v1/feedback", tags=["message-feedback"])


@message_feedback_router.get("/messages/{message_id}", response_model=MessageFeedbackResponse | None)
async def get_message_feedback(
    message_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> MessageFeedbackResponse | None:
    return await MessageFeedbackService(session).get_feedback(user_id=current_user.id, message_id=message_id)


@message_feedback_router.post("/messages/{message_id}", response_model=MessageFeedbackResponse)
async def upsert_message_feedback(
    message_id: UUID,
    request: MessageFeedbackUpsertRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> MessageFeedbackResponse:
    return await MessageFeedbackService(session).upsert_feedback(
        user_id=current_user.id,
        message_id=message_id,
        request=request,
    )
