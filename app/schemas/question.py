"""Schema模块：question。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.question_bank import QuestionType
from app.services.question_rules import CHOICE_OPTION_LABELS


class QuestionOption(BaseModel):
    label: str = Field(..., min_length=1, max_length=1)
    text: str = Field(..., min_length=1)

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if normalized not in CHOICE_OPTION_LABELS:
            raise ValueError("Option label must be one of A, B, C, D")
        return normalized

    @field_validator("text", mode="before")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Option text cannot be empty")
        return normalized


class QuestionBankCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class QuestionBankUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class QuestionBankResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    total_questions: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuestionBankListResponse(BaseModel):
    items: list[QuestionBankResponse]
    total: int


class QuestionCreate(BaseModel):
    bank_id: UUID
    external_id: str | None = Field(default=None, max_length=255)
    question_text: str = Field(..., min_length=1)
    question_type: QuestionType
    options: list[QuestionOption] | None = None
    answer: str | None = None
    explanation: str | None = None
    knowledge_point_ids: list[UUID] = Field(default_factory=list)


class QuestionUpdate(BaseModel):
    question_text: str | None = Field(default=None, min_length=1)
    question_type: QuestionType | None = None
    options: list[QuestionOption] | None = None
    answer: str | None = None
    explanation: str | None = None


class QuestionImportItem(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    question_text: str = Field(..., min_length=1)
    question_type: QuestionType
    options: list[QuestionOption] | None = None
    answer: str = Field(..., min_length=1)
    explanation: str | None = None
    knowledge_point_titles: list[str] = Field(default_factory=list)


class QuestionImportRequest(BaseModel):
    bank_id: UUID
    questions: list[QuestionImportItem] = Field(..., min_length=1, max_length=1000)


class QuestionVectorizeRequest(BaseModel):
    only_dirty: bool = True
    batch_size: int = Field(default=10, ge=1, le=100)


class QuestionKnowledgePointLink(BaseModel):
    knowledge_point_ids: list[UUID] = Field(default_factory=list)


class QuestionResponse(BaseModel):
    id: UUID
    bank_id: UUID
    external_id: str | None
    content_hash: str
    question_text: str
    question_type: QuestionType
    options: list[dict] | None
    answer: str | None
    explanation: str | None
    knowledge_point_ids: list[UUID] = Field(default_factory=list)
    is_dirty: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    total: int
    page: int
    page_size: int


class QuestionImportResponse(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class VectorizationJobResponse(BaseModel):
    id: UUID
    status: str
    progress: int
    total_questions: int
    processed_questions: int
    celery_task_id: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VectorizationJobListResponse(BaseModel):
    items: list[VectorizationJobResponse]
    total: int
    page: int
    page_size: int


class VectorizationJobRetryResponse(BaseModel):
    job_id: UUID
    new_job_id: UUID
    status: str
    message: str
