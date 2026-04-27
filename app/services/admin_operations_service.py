"""Admin operations console and quality radar service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.repositories.ingestion_job_repo import IngestionJobRepository
from app.repositories.quality_repo import QualityRepository
from app.repositories.question_repo import VectorizationJobRepository
from app.schemas.admin_operations import AdminTaskConsoleItem, ContentQualityWarning, QualityRadarResponse


class AdminOperationsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ingestion_jobs = IngestionJobRepository(session)
        self.vectorization_jobs = VectorizationJobRepository(session)
        self.quality = QualityRepository(session)

    async def list_tasks(
        self,
        *,
        page: int,
        page_size: int,
        task_type: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> tuple[list[AdminTaskConsoleItem], int, dict[str, int]]:
        requested_status = JobStatus(str(status)) if status else None
        items: list[AdminTaskConsoleItem] = []
        total = 0
        if task_type in (None, "ingestion"):
            ingestion, ingestion_total = await self.ingestion_jobs.list_jobs(
                page=page if task_type == "ingestion" else 1,
                page_size=page_size,
                status=requested_status,
                q=q,
            )
            total += ingestion_total
            items.extend(
                AdminTaskConsoleItem(
                    id=job.id,
                    task_type="ingestion",
                    status=job.status.value if hasattr(job.status, "value") else str(job.status),
                    progress=job.progress,
                    title=job.object_path,
                    resource_id=job.knowledge_point_id,
                    celery_task_id=job.celery_task_id,
                    error_message=job.error_message,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    metadata={"file_type": job.file_type},
                )
                for job in ingestion
            )
        if task_type in (None, "vectorization"):
            vector_jobs, vector_total = await self.vectorization_jobs.list_jobs(
                page=page if task_type == "vectorization" else 1,
                page_size=page_size,
                status=requested_status,
            )
            total += vector_total
            items.extend(
                AdminTaskConsoleItem(
                    id=job.id,
                    task_type="vectorization",
                    status=job.status.value if hasattr(job.status, "value") else str(job.status),
                    progress=job.progress,
                    title=f"Question vectorization · {job.processed_questions}/{job.total_questions}",
                    resource_id=None,
                    celery_task_id=job.celery_task_id,
                    error_message=job.error_message,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    metadata={"total_questions": job.total_questions, "processed_questions": job.processed_questions},
                )
                for job in vector_jobs
            )
        items = sorted(items, key=lambda item: item.created_at, reverse=True)
        if task_type is None:
            start = (page - 1) * page_size
            items = items[start : start + page_size]
        summary = {
            "failed_ingestion_jobs": await self.quality.count_failed_ingestion_jobs(),
            "failed_vectorization_jobs": await self.quality.count_failed_vectorization_jobs(),
        }
        return items, total, summary

    async def quality_radar(self) -> QualityRadarResponse:
        document_count = await self.quality.count_knowledge_points()
        active_document_count = await self.quality.count_knowledge_points(active_only=True)
        chunk_count = await self.quality.count_chunks()
        vectorized_chunk_count = await self.quality.count_chunks(vectorized_only=True)
        question_count = await self.quality.count_questions()
        vectorized_question_count = await self.quality.count_questions(vectorized_only=True)
        dirty_question_count = await self.quality.count_questions(dirty_only=True)
        failed_ingestion_jobs = await self.quality.count_failed_ingestion_jobs()
        failed_vectorization_jobs = await self.quality.count_failed_vectorization_jobs()

        warnings: list[ContentQualityWarning] = []
        if active_document_count and vectorized_chunk_count == 0:
            warnings.append(ContentQualityWarning(
                code="NO_VECTORIZED_CHUNKS",
                severity="critical",
                title="知识库缺少可检索向量",
                detail="存在激活文档，但没有任何已向量化分块。",
                resource_type="knowledge_point",
            ))
        if question_count and dirty_question_count:
            warnings.append(ContentQualityWarning(
                code="DIRTY_QUESTIONS",
                severity="warning",
                title="题库存在待向量化题目",
                detail=f"{dirty_question_count} 道题需要重新向量化。",
                resource_type="question",
            ))
        if failed_ingestion_jobs:
            warnings.append(ContentQualityWarning(
                code="FAILED_INGESTION_JOBS",
                severity="warning",
                title="存在失败的文档入库任务",
                detail=f"{failed_ingestion_jobs} 个入库任务失败，可在任务控制台重试。",
                resource_type="ingestion_job",
            ))
        if failed_vectorization_jobs:
            warnings.append(ContentQualityWarning(
                code="FAILED_VECTORIZATION_JOBS",
                severity="warning",
                title="存在失败的题库向量化任务",
                detail=f"{failed_vectorization_jobs} 个向量化任务失败。",
                resource_type="vectorization_job",
            ))

        return QualityRadarResponse(
            document_count=document_count,
            active_document_count=active_document_count,
            chunk_count=chunk_count,
            vectorized_chunk_count=vectorized_chunk_count,
            question_count=question_count,
            vectorized_question_count=vectorized_question_count,
            dirty_question_count=dirty_question_count,
            failed_ingestion_jobs=failed_ingestion_jobs,
            failed_vectorization_jobs=failed_vectorization_jobs,
            warnings=warnings,
        )
