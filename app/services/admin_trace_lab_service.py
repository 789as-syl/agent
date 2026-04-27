"""Admin Trace Lab service with redacted timeline projection."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.trace_projector import project_run_event
from app.core.exceptions import NotFoundError
from app.repositories.chat_run_repo import ChatRunRepository
from app.repositories.run_event_repo import RunEventRepository
from app.schemas.admin_trace_lab import AdminTraceRunSummary, AdminTraceTimelineItem


class AdminTraceLabService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.run_repo = ChatRunRepository(session)
        self.event_repo = RunEventRepository(session)

    async def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> tuple[list[AdminTraceRunSummary], int]:
        rows, total = await self.run_repo.list_admin_runs(
            page=page,
            page_size=page_size,
            user_id=user_id,
            conversation_id=conversation_id,
            status=status,
            q=q,
        )
        return [self._summarize_run(run, event_count) for run, event_count in rows], total

    async def get_run_detail(
        self,
        *,
        run_id: UUID,
        after_event_id: str | None = None,
        limit: int = 200,
    ) -> tuple[AdminTraceRunSummary, list[AdminTraceTimelineItem], str | None, bool]:
        run = await self.run_repo.get_by_id(run_id)
        if not run:
            raise NotFoundError(error_code="CHAT_RUN_NOT_FOUND", message="Chat run not found")

        if after_event_id:
            rows, anchor_found = await self.event_repo.list_after_event_id(run_id, after_event_id, limit=limit)
        else:
            rows = await self.event_repo.list_by_run_id(run_id, limit=limit)
            anchor_found = True
        summary = self._summarize_run(run, len(rows))
        events = [AdminTraceTimelineItem.model_validate(project_run_event(row)) for row in rows]
        last_event_id = events[-1].event_id if events else after_event_id
        return summary, events, last_event_id, anchor_found

    @staticmethod
    def _summarize_run(run: Any, event_count: int) -> AdminTraceRunSummary:
        return AdminTraceRunSummary(
            id=run.id,
            conversation_id=run.conversation_id,
            user_id=run.user_id,
            query=run.query,
            status=run.status.value if hasattr(run.status, "value") else str(run.status),
            parent_run_id=run.parent_run_id,
            retry_of_run_id=run.retry_of_run_id,
            event_count=event_count,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
