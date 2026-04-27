"""Append-only admin audit service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.admin_audit_log_repo import AdminAuditLogRepository


class AdminAuditService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AdminAuditLogRepository(session)

    async def record(
        self,
        *,
        actor_user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str | UUID | None,
        summary: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        await self.repo.create(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            summary=summary,
            metadata_json=metadata_json or {},
        )

    async def list_logs(
        self,
        *,
        page: int,
        page_size: int,
        action: str | None = None,
        resource_type: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> tuple[list, int]:
        return await self.repo.list_logs(
            page=page,
            page_size=page_size,
            action=action,
            resource_type=resource_type,
            actor_user_id=actor_user_id,
        )
