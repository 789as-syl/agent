"""Schema module: ingestion."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.file_types import normalize_file_type


class PresignUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_type: str = Field(..., description="file extension or MIME type")
    file_size: int | None = Field(default=None, ge=0)

    @field_validator("file_type", mode="before")
    @classmethod
    def _normalize_file_type(cls, value: str) -> str:
        return normalize_file_type(str(value))


class PresignUploadResponse(BaseModel):
    upload_url: str
    object_path: str
    expires_in: int


class UploadCallbackRequest(BaseModel):
    object_path: str
    file_name: str
    file_type: str
    file_size: int = Field(..., ge=0)

    @field_validator("file_type", mode="before")
    @classmethod
    def _normalize_file_type(cls, value: str) -> str:
        return normalize_file_type(str(value))


class UploadCallbackResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


class KnowledgePointCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    file_type: str = Field(..., description="content type")

    @field_validator("file_type", mode="before")
    @classmethod
    def _normalize_file_type(cls, value: str) -> str:
        return normalize_file_type(str(value))


class KnowledgePointUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class KnowledgePointChunkResponse(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    metadata_json: dict
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class KnowledgePointResponse(BaseModel):
    id: UUID
    title: str
    file_type: str
    object_path: str
    version: int = 1
    is_active: bool
    document_metadata_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    chunks: list[KnowledgePointChunkResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class KnowledgePointListResponse(BaseModel):
    items: list[KnowledgePointResponse]
    total: int
    page: int
    page_size: int


class KnowledgePointDeleteResponse(BaseModel):
    knowledge_point_id: UUID
    deleted_chunk_count: int = 0
    detached_job_count: int = 0
    revoked_task_count: int = 0
    object_deleted: bool = True
    message: str


class IngestionJobResponse(BaseModel):
    id: UUID
    knowledge_point_id: UUID | None
    object_path: str
    file_type: str
    status: str
    progress: int
    error_message: str | None
    celery_task_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IngestionJobRetryResponse(BaseModel):
    job_id: UUID
    new_job_id: UUID
    status: str
    message: str


class IngestionJobListResponse(BaseModel):
    items: list[IngestionJobResponse]
    total: int
    page: int
    page_size: int


class KnowledgePointDocumentUrlResponse(BaseModel):
    url: str
    object_path: str
    file_type: str
    expires_in: int
    source_url: str
    source_object_path: str
    source_file_type: str
    preview_url: str | None = None
    preview_object_path: str | None = None
    preview_file_type: str | None = None
    preview_available: bool = False
    preview_from_source: bool = False
    preview_status: str | None = None
    preview_message: str | None = None
    preview_error: str | None = None
    preview_retrying: bool = False
    preview_metadata: dict = Field(default_factory=dict)
