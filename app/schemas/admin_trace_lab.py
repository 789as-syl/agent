"""Admin Trace Lab schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AdminTraceRunSummary(BaseModel):
    id: UUID
    conversation_id: UUID
    user_id: UUID
    query: str
    status: str
    parent_run_id: UUID | None = None
    retry_of_run_id: UUID | None = None
    event_count: int = 0
    created_at: datetime
    updated_at: datetime


class AdminTraceRunListResponse(BaseModel):
    items: list[AdminTraceRunSummary]
    total: int
    page: int
    page_size: int


class AdminTraceTimelineItem(BaseModel):
    event_id: str
    event_type: str
    step: int
    sequence_no: int | None = None
    timestamp: str | None = None
    title: str
    kind: str
    status: str
    detail_sanitized: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    redacted: bool = False


class AdminTraceRunDetailResponse(BaseModel):
    run: AdminTraceRunSummary
    events: list[AdminTraceTimelineItem]
    after_event_id: str | None = None
    anchor_found: bool = True
    last_event_id: str | None = None
    redaction_policy: str
