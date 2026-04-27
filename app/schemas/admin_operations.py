"""Admin operations, quality radar, and RAG eval schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AdminTaskConsoleItem(BaseModel):
    id: UUID
    task_type: Literal["ingestion", "vectorization"]
    status: str
    progress: int
    title: str
    resource_id: UUID | None = None
    celery_task_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminTaskConsoleResponse(BaseModel):
    items: list[AdminTaskConsoleItem]
    total: int
    page: int
    page_size: int
    summary: dict[str, int] = Field(default_factory=dict)


class ContentQualityWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"] = "warning"
    title: str
    detail: str
    resource_type: str
    resource_id: str | None = None


class QualityRadarResponse(BaseModel):
    document_count: int = 0
    active_document_count: int = 0
    chunk_count: int = 0
    vectorized_chunk_count: int = 0
    question_count: int = 0
    vectorized_question_count: int = 0
    dirty_question_count: int = 0
    failed_ingestion_jobs: int = 0
    failed_vectorization_jobs: int = 0
    warnings: list[ContentQualityWarning] = Field(default_factory=list)


class RagGoldenQueryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    query: str = Field(..., min_length=1, max_length=2000)
    expected_answer: str | None = Field(default=None, max_length=5000)
    expected_source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RagGoldenQueryResponse(BaseModel):
    id: UUID
    name: str
    query: str
    expected_answer: str | None = None
    expected_source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_active: bool
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RagGoldenQueryListResponse(BaseModel):
    items: list[RagGoldenQueryResponse]
    total: int
    page: int
    page_size: int


class RagEvalRunCreate(BaseModel):
    golden_query_id: UUID | None = None
    query: str | None = Field(default=None, min_length=1, max_length=2000)


class RagEvalRunResponse(BaseModel):
    id: UUID
    golden_query_id: UUID | None
    query: str
    status: str
    score: float
    evidence_count: int
    missing_expected_count: int
    result_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RagEvalRunListResponse(BaseModel):
    items: list[RagEvalRunResponse]
    total: int
    page: int
    page_size: int
