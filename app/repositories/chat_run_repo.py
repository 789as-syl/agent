"""Admin-facing chat-run repository helpers."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_run import ChatRun
from app.models.run_event import RunEvent


class ChatRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, run_id: UUID) -> ChatRun | None:
        return cast(ChatRun | None, await self.session.scalar(select(ChatRun).where(ChatRun.id == run_id)))

    async def list_admin_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> tuple[list[tuple[ChatRun, int]], int]:
        event_count = func.count(RunEvent.id).label("event_count")
        stmt = select(ChatRun, event_count).outerjoin(RunEvent, RunEvent.run_id == ChatRun.id).group_by(ChatRun.id)
        count_stmt = select(func.count()).select_from(ChatRun)

        conditions = []
        if user_id:
            conditions.append(ChatRun.user_id == user_id)
        if conversation_id:
            conditions.append(ChatRun.conversation_id == conversation_id)
        if status:
            conditions.append(ChatRun.status == status)
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(or_(ChatRun.query.ilike(pattern)))

        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(ChatRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], int(row[1] or 0)) for row in rows], total
