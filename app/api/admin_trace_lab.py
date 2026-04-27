# ruff: noqa: B008
"""Admin Trace Lab API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.models.user import User
from app.schemas.admin_trace_lab import AdminTraceRunDetailResponse, AdminTraceRunListResponse
from app.services.admin_trace_lab_service import AdminTraceLabService

admin_trace_lab_router = APIRouter(prefix="/api/v1/admin", tags=["admin-trace-lab"])
_REDACTION_POLICY = "redact raw reasoning, provider payloads, tool protocol envelopes, and chain-of-thought fields"


@admin_trace_lab_router.get("/trace-runs", response_model=AdminTraceRunListResponse)
async def list_trace_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID | None = Query(default=None),
    conversation_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminTraceRunListResponse:
    _ = current_user
    items, total = await AdminTraceLabService(session).list_runs(
        page=page,
        page_size=page_size,
        user_id=user_id,
        conversation_id=conversation_id,
        status=status,
        q=q,
    )
    return AdminTraceRunListResponse(items=items, total=total, page=page, page_size=page_size)


@admin_trace_lab_router.get("/trace-runs/{run_id}", response_model=AdminTraceRunDetailResponse)
async def get_trace_run(
    run_id: UUID,
    after_event_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminTraceRunDetailResponse:
    _ = current_user
    run, events, last_event_id, anchor_found = await AdminTraceLabService(session).get_run_detail(
        run_id=run_id,
        after_event_id=after_event_id,
        limit=limit,
    )
    return AdminTraceRunDetailResponse(
        run=run,
        events=events,
        after_event_id=after_event_id,
        anchor_found=anchor_found,
        last_event_id=last_event_id,
        redaction_policy=_REDACTION_POLICY,
    )
