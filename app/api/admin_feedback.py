# ruff: noqa: B008
"""Admin review surface for user message feedback."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.models.user import User
from app.schemas.feedback import AdminMessageFeedbackListResponse, AdminMessageFeedbackSummaryResponse
from app.services.message_feedback_service import MessageFeedbackService

admin_feedback_router = APIRouter(prefix="/api/v1/admin", tags=["admin-feedback"])


@admin_feedback_router.get("/feedback", response_model=AdminMessageFeedbackListResponse)
async def list_message_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    rating: str | None = Query(default=None, pattern="^(helpful|not_helpful)$"),
    hallucination_flag: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminMessageFeedbackListResponse:
    _ = current_user
    return await MessageFeedbackService(session).list_feedback(
        page=page,
        page_size=page_size,
        rating=rating,
        hallucination_flag=hallucination_flag,
    )


@admin_feedback_router.get("/feedback/summary", response_model=AdminMessageFeedbackSummaryResponse)
async def summarize_message_feedback(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminMessageFeedbackSummaryResponse:
    _ = current_user
    return await MessageFeedbackService(session).summarize()
