"""Ingestion service layer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from celery.exceptions import CeleryError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.config import get_ingestion_supported_file_types
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError
from app.core.log_config import get_logger
from app.core.redis import redis_client
from app.models.enums import JobStatus
from app.models.ingestion_job import IngestionJob
from app.models.knowledge_point import KnowledgePoint
from app.repositories.ingestion_job_repo import IngestionJobRepository
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.services.admin_analytics_service import invalidate_admin_analytics_cache
from app.services.document_processing import is_ingestion_file_type_supported
from app.services.minio_service import MinIOService
from app.tasks.ingestion_tasks import process_document

logger = get_logger(__name__)

INGESTION_LOCK_PREFIX = "ingestion:lock:"
INGESTION_LOCK_TIMEOUT = 30
_SUPPORTED_INGESTION_TYPES = set(get_ingestion_supported_file_types())


class IngestionService:
    def __init__(self, session: AsyncSession, kp_repo: KnowledgePointRepository, job_repo: IngestionJobRepository):
        self.session = session
        self.kp_repo = kp_repo
        self.job_repo = job_repo

    async def create_upload_job(
        self,
        object_path: str,
        file_name: str,
        file_type: str,
        file_size: int,
    ) -> tuple[IngestionJob, KnowledgePoint]:
        normalized_type = file_type.lower()
        if normalized_type not in _SUPPORTED_INGESTION_TYPES:
            raise ValidationError(
                error_code="INGESTION_INVALID_FILE_TYPE",
                message=f"Unsupported file type: {file_type}",
            )
        if not is_ingestion_file_type_supported(normalized_type):
            raise ValidationError(
                error_code="INGESTION_PARSER_UNAVAILABLE",
                message=f"Parser for file type {normalized_type} is not available in current runtime",
            )

        if file_size <= 0:
            raise ValidationError(error_code="INGESTION_INVALID_FILE_SIZE", message="File size must be positive")
        if not object_path.startswith("documents/"):
            raise ValidationError(
                error_code="INGESTION_INVALID_OBJECT_PATH",
                message="Invalid object path",
            )

        lock_key = f"{INGESTION_LOCK_PREFIX}{object_path}"
        lock_acquired = await redis_client.set(lock_key, "1", nx=True, ex=INGESTION_LOCK_TIMEOUT)
        if not lock_acquired:
            raise ValidationError(
                error_code="INGESTION_IN_PROGRESS",
                message="Document is currently being processed, please wait",
            )

        try:
            try:
                object_stat = await MinIOService.stat_object(object_path)
            except Exception as exc:
                raise ValidationError(
                    error_code="INGESTION_OBJECT_NOT_FOUND",
                    message=f"Uploaded object not found or inaccessible: {exc}",
                ) from exc

            object_size = int(getattr(object_stat, "size", 0) or 0)
            if object_size <= 0:
                raise ValidationError(
                    error_code="INGESTION_EMPTY_OBJECT",
                    message="Uploaded object is empty",
                )
            if object_size != int(file_size):
                raise ValidationError(
                    error_code="INGESTION_FILE_SIZE_MISMATCH",
                    message="Uploaded object size does not match callback payload",
                    details={"expected": file_size, "actual": object_size},
                )

            existing = await self.kp_repo.get_active_by_object_path(object_path)
            if existing:
                raise ValidationError(
                    error_code="INGESTION_DUPLICATE_OBJECT",
                    message="Document already exists",
                )

            kp = await self.kp_repo.create(
                title=file_name,
                file_type=normalized_type,
                object_path=object_path,
                is_active=True,
            )

            job = await self.job_repo.create(
                knowledge_point_id=kp.id,
                object_path=object_path,
                file_type=normalized_type,
                status=JobStatus.PENDING,
                progress=0,
            )
            await self.session.commit()

            try:
                task = process_document.apply_async(args=[str(job.id)], task_id=f"ingestion_{job.id}")
            except CeleryError as exc:
                kp.is_active = False
                await self.job_repo.update_status(
                    job.id,
                    status=JobStatus.FAILED,
                    error_message=f"Failed to dispatch processing task: {exc}",
                )
                await self.session.commit()
                raise ValidationError(
                    error_code="INGESTION_TASK_DISPATCH_FAILED",
                    message=f"Failed to dispatch processing task: {exc}",
                ) from exc

            await self.job_repo.update_status(job.id, status=JobStatus.PENDING, celery_task_id=task.id)
            await self.session.commit()
            await invalidate_admin_analytics_cache()
            logger.info("Created ingestion job", job_id=str(job.id), knowledge_point_id=str(kp.id), file_size=file_size)
            return job, kp

        finally:
            await redis_client.delete(lock_key)

    async def retry_failed_job(
        self,
        job_id: UUID,
        user_id: UUID,
        retry_reason: str | None = None,
    ) -> tuple[IngestionJob, IngestionJob]:
        original_job = await self.job_repo.get_by_id(job_id)
        if not original_job:
            raise ValidationError(error_code="INGESTION_JOB_NOT_FOUND", message="Ingestion job not found")

        if original_job.status != JobStatus.FAILED:
            raise ValidationError(error_code="INGESTION_JOB_NOT_FAILED", message="Can only retry failed jobs")
        normalized_type = original_job.file_type.lower()
        if normalized_type not in _SUPPORTED_INGESTION_TYPES:
            raise ValidationError(
                error_code="INGESTION_INVALID_FILE_TYPE",
                message=f"Unsupported file type: {original_job.file_type}",
            )
        if not is_ingestion_file_type_supported(normalized_type):
            raise ValidationError(
                error_code="INGESTION_PARSER_UNAVAILABLE",
                message=f"Parser for file type {normalized_type} is not available in current runtime",
            )
        try:
            object_stat = await MinIOService.stat_object(original_job.object_path)
        except Exception as exc:
            raise ValidationError(
                error_code="INGESTION_OBJECT_NOT_FOUND",
                message=f"Uploaded object not found or inaccessible: {exc}",
            ) from exc
        if int(getattr(object_stat, "size", 0) or 0) <= 0:
            raise ValidationError(
                error_code="INGESTION_EMPTY_OBJECT",
                message="Uploaded object is empty",
            )

        lock_key = f"{INGESTION_LOCK_PREFIX}{original_job.object_path}"
        lock_acquired = await redis_client.set(lock_key, "1", nx=True, ex=INGESTION_LOCK_TIMEOUT)
        if not lock_acquired:
            raise ValidationError(
                error_code="INGESTION_IN_PROGRESS",
                message="Document is currently being processed, please wait",
            )

        try:
            _ = retry_reason  # placeholder for future audit persistence
            _ = user_id

            new_job = await self.job_repo.create(
                knowledge_point_id=original_job.knowledge_point_id,
                object_path=original_job.object_path,
                file_type=normalized_type,
                status=JobStatus.PENDING,
                progress=0,
            )
            await self.session.commit()

            try:
                task = process_document.apply_async(args=[str(new_job.id)], task_id=f"ingestion_{new_job.id}")
            except CeleryError as exc:
                await self.job_repo.update_status(
                    new_job.id,
                    status=JobStatus.FAILED,
                    error_message=f"Failed to dispatch retry task: {exc}",
                )
                await self.session.commit()
                raise ValidationError(
                    error_code="INGESTION_TASK_DISPATCH_FAILED",
                    message=f"Failed to dispatch retry task: {exc}",
                ) from exc

            await self.job_repo.update_status(new_job.id, status=JobStatus.PENDING, celery_task_id=task.id)
            await self.session.commit()
            await invalidate_admin_analytics_cache()
            logger.info(
                "Retried ingestion job",
                original_job_id=str(job_id),
                new_job_id=str(new_job.id),
                user_id=str(user_id),
            )
            return original_job, new_job

        finally:
            await redis_client.delete(lock_key)

    def log_if_job_stuck(self, job: IngestionJob, pending_threshold_seconds: int = 300) -> None:
        if job.status not in {JobStatus.PENDING, JobStatus.RUNNING}:
            return
        now = datetime.now(UTC)
        age_seconds = int((now - job.created_at).total_seconds())
        if age_seconds >= pending_threshold_seconds:
            logger.warning(
                "Ingestion job is pending/running for too long",
                job_id=str(job.id),
                status=job.status.value,
                age_seconds=age_seconds,
                celery_task_id=job.celery_task_id,
            )

    async def delete_knowledge_point(self, kp_id: UUID, user_id: UUID | None = None) -> dict[str, Any]:
        kp = await self.kp_repo.get_by_id(kp_id, include_chunks=False)
        if not kp:
            raise NotFoundError(error_code="KNOWLEDGE_POINT_NOT_FOUND", message="Knowledge point not found")

        lock_key = f"{INGESTION_LOCK_PREFIX}{kp.object_path}" if kp.object_path else None
        lock_acquired = True
        if lock_key:
            lock_acquired = bool(await redis_client.set(lock_key, "1", nx=True, ex=INGESTION_LOCK_TIMEOUT))
            if not lock_acquired:
                raise ConflictError(
                    error_code="KNOWLEDGE_POINT_DELETE_IN_PROGRESS",
                    message="Document is currently being processed, please wait before deleting it",
                )

        try:
            linked_jobs = await self.job_repo.list_by_knowledge_point_id(kp.id)
            detached_job_count = 0
            revoked_task_count = 0
            deletion_reason = "Knowledge point deleted by admin"

            for job in linked_jobs:
                is_active_job = job.status in {JobStatus.PENDING, JobStatus.RUNNING}
                if is_active_job and job.celery_task_id:
                    try:
                        celery_app.control.revoke(job.celery_task_id, terminate=False)
                        revoked_task_count += 1
                    except Exception as exc:  # pragma: no cover - defensive revoke logging
                        logger.warning(
                            "Failed to revoke ingestion task during knowledge point deletion",
                            job_id=str(job.id),
                            celery_task_id=job.celery_task_id,
                            error=str(exc),
                        )

                if job.knowledge_point_id is not None:
                    job.knowledge_point_id = None
                    detached_job_count += 1

                if is_active_job:
                    job.status = JobStatus.FAILED
                    job.progress = min(int(job.progress or 0), 99)
                    job.error_message = deletion_reason

                self.session.add(job)

            await self.session.flush()
            deleted_chunk_count = await self.kp_repo.count_chunks_by_kp_id(kp.id)

            preview_object_path = _extract_preview_object_path(kp.document_metadata_json)
            preview_object_deleted = True
            if preview_object_path and preview_object_path != kp.object_path:
                try:
                    await MinIOService.delete_object(preview_object_path)
                except Exception as exc:
                    if not _is_missing_object_error(exc):
                        raise ServiceUnavailableError(
                            message="Failed to delete document preview from object storage",
                            details={"object_path": preview_object_path, "error": str(exc)},
                        ) from exc
                    preview_object_deleted = False
                    logger.warning(
                        "Knowledge point preview artifact missing during deletion; continuing database cleanup",
                        knowledge_point_id=str(kp.id),
                        object_path=preview_object_path,
                        error=str(exc),
                    )

            object_deleted = True
            if kp.object_path:
                try:
                    await MinIOService.delete_object(kp.object_path)
                except Exception as exc:
                    if not _is_missing_object_error(exc):
                        raise ServiceUnavailableError(
                            message="Failed to delete document from object storage",
                            details={"object_path": kp.object_path, "error": str(exc)},
                        ) from exc
                    object_deleted = False
                    logger.warning(
                        "Knowledge point document missing during deletion; continuing database cleanup",
                        knowledge_point_id=str(kp.id),
                        object_path=kp.object_path,
                        error=str(exc),
                    )

            deleted = await self.kp_repo.delete(kp.id)
            if not deleted:
                raise NotFoundError(error_code="KNOWLEDGE_POINT_NOT_FOUND", message="Knowledge point not found")

            await self.session.commit()
            await invalidate_admin_analytics_cache()
            logger.info(
                "Deleted knowledge point",
                knowledge_point_id=str(kp.id),
                user_id=str(user_id) if user_id else None,
                deleted_chunk_count=deleted_chunk_count,
                detached_job_count=detached_job_count,
                revoked_task_count=revoked_task_count,
                object_deleted=object_deleted,
                preview_object_deleted=preview_object_deleted,
            )
            return {
                "knowledge_point_id": kp.id,
                "deleted_chunk_count": deleted_chunk_count,
                "detached_job_count": detached_job_count,
                "revoked_task_count": revoked_task_count,
                "object_deleted": object_deleted,
                "message": "Knowledge point deleted successfully",
            }
        finally:
            if lock_key and lock_acquired:
                await redis_client.delete(lock_key)


def _is_missing_object_error(exc: Exception) -> bool:
    code = str(getattr(exc, "code", "") or "").strip()
    if code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
        return True
    return "NoSuchKey" in str(exc) or "NoSuchObject" in str(exc)


def _extract_preview_object_path(document_metadata: dict[str, Any] | None) -> str | None:
    metadata = dict(document_metadata or {})
    preview = metadata.get("preview_artifact", {})
    if not isinstance(preview, dict):
        return None
    object_path = str(preview.get("object_path") or "").strip()
    return object_path or None
