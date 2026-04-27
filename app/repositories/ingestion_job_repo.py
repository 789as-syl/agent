"""????: ingestion_job_repo?"""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.ingestion_job import IngestionJob

_UNSET: Any = object()


class IngestionJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs: Any) -> IngestionJob:
        job = IngestionJob(**kwargs)
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> IngestionJob | None:
        result = await self.session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        return result.scalar_one_or_none()

    async def list_by_knowledge_point_id(self, knowledge_point_id: uuid.UUID) -> list[IngestionJob]:
        result = await self.session.execute(
            select(IngestionJob)
            .where(IngestionJob.knowledge_point_id == knowledge_point_id)
            .order_by(IngestionJob.created_at.desc())
        )
        return list(result.scalars().all())


    async def list_jobs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: JobStatus | str | None = None,
        q: str | None = None,
    ) -> tuple[list[IngestionJob], int]:
        stmt = select(IngestionJob)
        count_stmt = select(func.count()).select_from(IngestionJob)

        if status is not None:
            status_value = status if isinstance(status, JobStatus) else JobStatus(str(status))
            stmt = stmt.where(IngestionJob.status == status_value)
            count_stmt = count_stmt.where(IngestionJob.status == status_value)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(IngestionJob.object_path.ilike(pattern))
            count_stmt = count_stmt.where(IngestionJob.object_path.ilike(pattern))

        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(IngestionJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus | str | None = None,
        progress: int | None = None,
        error_message: str | None | object = _UNSET,
        celery_task_id: str | None | object = _UNSET,
    ) -> IngestionJob | None:
        job = await self.get_by_id(job_id)
        if not job:
            return None

        if status is not None:
            status_value = status if isinstance(status, JobStatus) else JobStatus(str(status))
            job.status = status_value

        if progress is not None:
            job.progress = progress
        if error_message is not _UNSET:
            job.error_message = cast(str | None, error_message)
        if celery_task_id is not _UNSET:
            job.celery_task_id = cast(str | None, celery_task_id)

        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job
