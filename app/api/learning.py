# ruff: noqa: B008
"""User learning loop routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_user
from app.models.user import User
from app.schemas.learning import (
    LearningPathResponse,
    MasteryRecordListResponse,
    PracticeSessionCreate,
    PracticeSessionListResponse,
    PracticeSessionResponse,
    PracticeSubmitRequest,
    PracticeSubmitResponse,
    ReviewCardListResponse,
    WrongQuestionListResponse,
)
from app.services.learning_service import LearningService

learning_router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


@learning_router.post("/practice-sessions", response_model=PracticeSessionResponse)
async def create_practice_session(
    request: PracticeSessionCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> PracticeSessionResponse:
    return await LearningService(session).create_practice_session(user_id=current_user.id, request=request)


@learning_router.get("/practice-sessions", response_model=PracticeSessionListResponse)
async def list_practice_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> PracticeSessionListResponse:
    return await LearningService(session).list_practice_sessions(user_id=current_user.id, page=page, page_size=page_size)


@learning_router.get("/practice-sessions/{session_id}", response_model=PracticeSessionResponse)
async def get_practice_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> PracticeSessionResponse:
    return await LearningService(session).get_practice_session(user_id=current_user.id, session_id=session_id)


@learning_router.post("/practice-sessions/{session_id}/submit", response_model=PracticeSubmitResponse)
async def submit_practice_answer(
    session_id: UUID,
    request: PracticeSubmitRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> PracticeSubmitResponse:
    return await LearningService(session).submit_practice_answer(
        user_id=current_user.id,
        session_id=session_id,
        question_id=request.question_id,
        answer=request.answer,
    )


@learning_router.get("/wrong-questions", response_model=WrongQuestionListResponse)
async def list_wrong_questions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WrongQuestionListResponse:
    return await LearningService(session).list_wrong_questions(user_id=current_user.id, page=page, page_size=page_size)


@learning_router.get("/mastery", response_model=MasteryRecordListResponse)
async def list_mastery(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> MasteryRecordListResponse:
    return await LearningService(session).list_mastery(user_id=current_user.id)


@learning_router.get("/review-cards", response_model=ReviewCardListResponse)
async def list_review_cards(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> ReviewCardListResponse:
    return await LearningService(session).list_review_cards(user_id=current_user.id, page=page, page_size=page_size)


@learning_router.get("/path", response_model=LearningPathResponse)
async def get_learning_path(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> LearningPathResponse:
    return await LearningService(session).learning_path(user_id=current_user.id)
