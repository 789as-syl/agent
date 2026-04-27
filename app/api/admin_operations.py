# ruff: noqa: B008
"""Admin operations and quality radar routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.models.user import User
from app.schemas.admin_operations import AdminTaskConsoleResponse, QualityRadarResponse
from app.services.admin_operations_service import AdminOperationsService

admin_operations_router = APIRouter(prefix="/api/v1/admin", tags=["admin-operations"])


@admin_operations_router.get("/tasks", response_model=AdminTaskConsoleResponse)
async def list_admin_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    task_type: str | None = Query(default=None, pattern="^(ingestion|vectorization)$"),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminTaskConsoleResponse:
    _ = current_user
    items, total, summary = await AdminOperationsService(session).list_tasks(
        page=page,
        page_size=page_size,
        task_type=task_type,
        status=status,
        q=q,
    )
    return AdminTaskConsoleResponse(items=items, total=total, page=page, page_size=page_size, summary=summary)


@admin_operations_router.get("/quality-radar", response_model=QualityRadarResponse)
async def get_quality_radar(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> QualityRadarResponse:
    _ = current_user
    return await AdminOperationsService(session).quality_radar()
