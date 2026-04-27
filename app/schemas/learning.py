"""User learning-loop schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PracticeSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    question_ids: list[UUID] = Field(default_factory=list)
    knowledge_point_id: UUID | None = None
    limit: int = Field(default=10, ge=1, le=50)


class PracticeQuestionView(BaseModel):
    id: UUID
    question_text: str
    question_type: str
    options: list[dict] | None = None
    knowledge_point_ids: list[UUID] = Field(default_factory=list)


class PracticeSessionResponse(BaseModel):
    id: UUID
    title: str
    status: str
    source_type: str | None = None
    source_id: str | None = None
    question_ids: list[UUID] = Field(default_factory=list)
    current_index: int
    total_questions: int
    correct_count: int
    score: float
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    questions: list[PracticeQuestionView] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PracticeSessionListResponse(BaseModel):
    items: list[PracticeSessionResponse]
    total: int
    page: int
    page_size: int


class PracticeSubmitRequest(BaseModel):
    question_id: UUID
    answer: str = Field(..., min_length=1, max_length=5000)


class PracticeAttemptResponse(BaseModel):
    id: UUID
    session_id: UUID
    question_id: UUID
    submitted_answer: str
    correct_answer: str | None
    is_correct: bool
    explanation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PracticeSubmitResponse(BaseModel):
    attempt: PracticeAttemptResponse
    session: PracticeSessionResponse
    wrong_question_updated: bool
    review_card_due_at: datetime | None = None


class WrongQuestionResponse(BaseModel):
    id: UUID
    question_id: UUID
    question_text: str
    wrong_count: int
    last_answer: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WrongQuestionListResponse(BaseModel):
    items: list[WrongQuestionResponse]
    total: int
    page: int
    page_size: int


class MasteryRecordResponse(BaseModel):
    id: UUID
    question_id: UUID | None = None
    knowledge_point_id: UUID | None = None
    mastery_score: float
    attempts_count: int
    correct_count: int
    last_practiced_at: datetime | None = None

    model_config = {"from_attributes": True}


class MasteryRecordListResponse(BaseModel):
    items: list[MasteryRecordResponse]
    total: int


class ReviewCardResponse(BaseModel):
    id: UUID
    question_id: UUID
    question_text: str
    status: str
    due_at: datetime
    interval_days: int
    ease_factor: float
    last_result: str | None = None


class ReviewCardListResponse(BaseModel):
    items: list[ReviewCardResponse]
    total: int
    page: int
    page_size: int


class LearningPathItemResponse(BaseModel):
    id: UUID
    knowledge_point_id: UUID | None = None
    question_id: UUID | None = None
    title: str
    status: str
    priority: int
    reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LearningPathResponse(BaseModel):
    items: list[LearningPathItemResponse]
    total: int
