# ruff: noqa: B008
"""Admin audit log API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.models.user import User
from app.schemas.admin_audit import AdminAuditLogListResponse, AdminAuditLogResponse
from app.services.admin_audit_service import AdminAuditService

admin_audit_router = APIRouter(prefix="/api/v1/admin", tags=["admin-audit"])


@admin_audit_router.get("/audit-logs", response_model=AdminAuditLogListResponse)
async def list_admin_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    actor_user_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> AdminAuditLogListResponse:
    _ = current_user
    items, total = await AdminAuditService(session).list_logs(
        page=page,
        page_size=page_size,
        action=action,
        resource_type=resource_type,
        actor_user_id=actor_user_id,
    )
    return AdminAuditLogListResponse(
        items=[AdminAuditLogResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
