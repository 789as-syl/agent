"""Read models for admin task console and quality radar."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.ingestion_job import IngestionJob
from app.models.knowledge_point import KnowledgePoint, KnowledgePointChunk
from app.models.question_bank import Question
from app.models.vectorization_job import VectorizationJob


class QualityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_knowledge_points(self, *, active_only: bool = False) -> int:
        stmt = select(func.count()).select_from(KnowledgePoint)
        if active_only:
            stmt = stmt.where(KnowledgePoint.is_active.is_(True))
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def count_chunks(self, *, vectorized_only: bool = False) -> int:
        stmt = select(func.count()).select_from(KnowledgePointChunk)
        if vectorized_only:
            stmt = stmt.where(KnowledgePointChunk.embedding.is_not(None))
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def count_questions(self, *, vectorized_only: bool = False, dirty_only: bool = False) -> int:
        stmt = select(func.count()).select_from(Question)
        if vectorized_only:
            stmt = stmt.where(
                Question.question_embedding.is_not(None),
                Question.is_dirty.is_(False),
                Question.embedding_text_hash.is_not(None),
            )
        if dirty_only:
            stmt = stmt.where(Question.is_dirty.is_(True))
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def count_failed_ingestion_jobs(self) -> int:
        stmt = select(func.count()).select_from(IngestionJob).where(IngestionJob.status == JobStatus.FAILED)
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def count_failed_vectorization_jobs(self) -> int:
        stmt = select(func.count()).select_from(VectorizationJob).where(VectorizationJob.status == JobStatus.FAILED)
        return int((await self.session.execute(stmt)).scalar() or 0)
