"""Repositories for RAG Eval Lab."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_eval import RagEvalRun, RagGoldenQuery


class RagGoldenQueryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs: Any) -> RagGoldenQuery:
        item = RagGoldenQuery(**kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def get_by_id(self, item_id: UUID) -> RagGoldenQuery | None:
        return cast(RagGoldenQuery | None, await self.session.scalar(select(RagGoldenQuery).where(RagGoldenQuery.id == item_id)))

    async def list_items(self, *, page: int, page_size: int, active_only: bool = True) -> tuple[list[RagGoldenQuery], int]:
        stmt = select(RagGoldenQuery)
        count_stmt = select(func.count()).select_from(RagGoldenQuery)
        if active_only:
            stmt = stmt.where(RagGoldenQuery.is_active.is_(True))
            count_stmt = count_stmt.where(RagGoldenQuery.is_active.is_(True))
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(RagGoldenQuery.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list((await self.session.execute(stmt)).scalars().all()), total

    async def soft_delete(self, item: RagGoldenQuery) -> RagGoldenQuery:
        item.is_active = False
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item


class RagEvalRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs: Any) -> RagEvalRun:
        item = RagEvalRun(**kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def get_by_id(self, item_id: UUID) -> RagEvalRun | None:
        return cast(RagEvalRun | None, await self.session.scalar(select(RagEvalRun).where(RagEvalRun.id == item_id)))

    async def list_items(self, *, page: int, page_size: int) -> tuple[list[RagEvalRun], int]:
        total = int((await self.session.execute(select(func.count()).select_from(RagEvalRun))).scalar() or 0)
        stmt = select(RagEvalRun).order_by(RagEvalRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list((await self.session.execute(stmt)).scalars().all()), total
