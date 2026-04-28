"""Schemas for user answer feedback."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

FeedbackRating = Literal["helpful", "not_helpful"]
FeedbackEvidenceQuality = Literal["sufficient", "insufficient", "missing"]


class MessageFeedbackUpsertRequest(BaseModel):
    rating: FeedbackRating
    evidence_quality: FeedbackEvidenceQuality | None = None
    hallucination_flag: bool = False
    comment: str | None = Field(default=None, max_length=2000)


class MessageFeedbackResponse(BaseModel):
    id: UUID
    user_id: UUID
    conversation_id: UUID
    message_id: UUID
    run_id: UUID | None = None
    rating: FeedbackRating
    evidence_quality: FeedbackEvidenceQuality | None = None
    hallucination_flag: bool
    comment: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminMessageFeedbackItem(BaseModel):
    id: UUID
    user_id: UUID
    user_phone: str
    conversation_id: UUID
    message_id: UUID
    run_id: UUID | None = None
    rating: FeedbackRating
    evidence_quality: FeedbackEvidenceQuality | None = None
    hallucination_flag: bool
    comment: str | None = None
    message_preview: str
    created_at: datetime
    updated_at: datetime


class AdminMessageFeedbackListResponse(BaseModel):
    items: list[AdminMessageFeedbackItem]
    total: int
    page: int
    page_size: int


class AdminMessageFeedbackSummaryResponse(BaseModel):
    total_feedback: int = 0
    helpful_count: int = 0
    not_helpful_count: int = 0
    hallucination_count: int = 0
    evidence_missing_count: int = 0
    evidence_insufficient_count: int = 0
    comment_count: int = 0
