"""Run event repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run_event import RunEvent


class RunEventRepository:
    """Append-only repository for run transcript events."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, run_event: RunEvent) -> RunEvent:
        self.session.add(run_event)
        await self.session.flush()
        return run_event

    async def create_many(self, run_events: list[RunEvent]) -> list[RunEvent]:
        if not run_events:
            return []
        self.session.add_all(run_events)
        await self.session.flush()
        return run_events

    async def list_by_run_id(self, run_id: UUID, limit: int | None = None) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.step.asc(), RunEvent.sequence_no.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_after_event_id(
        self,
        run_id: UUID,
        event_id: str,
        limit: int | None = None,
    ) -> tuple[list[RunEvent], bool]:
        anchor_result = await self.session.execute(
            select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.event_id == event_id)
        )
        anchor = anchor_result.scalar_one_or_none()
        if anchor is None:
            return [], False

        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .where(
                or_(
                    RunEvent.step > anchor.step,
                    and_(RunEvent.step == anchor.step, RunEvent.sequence_no > anchor.sequence_no),
                )
            )
            .order_by(RunEvent.step.asc(), RunEvent.sequence_no.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), True
