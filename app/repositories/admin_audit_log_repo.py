"""Repository for admin audit logs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog


class AdminAuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        actor_user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str | None,
        summary: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> AdminAuditLog:
        log = AdminAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            metadata_json=metadata_json or {},
        )
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log

    async def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        action: str | None = None,
        resource_type: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> tuple[list[AdminAuditLog], int]:
        stmt = select(AdminAuditLog)
        count_stmt = select(func.count()).select_from(AdminAuditLog)
        if action:
            stmt = stmt.where(AdminAuditLog.action == action)
            count_stmt = count_stmt.where(AdminAuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AdminAuditLog.resource_type == resource_type)
            count_stmt = count_stmt.where(AdminAuditLog.resource_type == resource_type)
        if actor_user_id:
            stmt = stmt.where(AdminAuditLog.actor_user_id == actor_user_id)
            count_stmt = count_stmt.where(AdminAuditLog.actor_user_id == actor_user_id)

        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(AdminAuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total
