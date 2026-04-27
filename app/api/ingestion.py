# ruff: noqa: B008
"""Ingestion admin endpoints."""

from __future__ import annotations

from uuid import UUID

from celery.exceptions import CeleryError
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_session, get_current_admin_user
from app.core.config import get_ingestion_supported_file_types, settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import JobStatus
from app.models.user import User
from app.repositories.ingestion_job_repo import IngestionJobRepository
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.schemas.ingestion import (
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionJobRetryResponse,
    KnowledgePointCreate,
    KnowledgePointDeleteResponse,
    KnowledgePointDocumentUrlResponse,
    KnowledgePointListResponse,
    KnowledgePointResponse,
    KnowledgePointUpdate,
    PresignUploadRequest,
    PresignUploadResponse,
    UploadCallbackRequest,
    UploadCallbackResponse,
)
from app.services.admin_audit_service import AdminAuditService
from app.services.document_processing import is_ingestion_file_type_supported
from app.services.ingestion_service import IngestionService
from app.services.minio_service import MinIOService
from app.tasks.ingestion_tasks import process_document

admin_ingestion_router = APIRouter(prefix="/api/v1/admin", tags=["admin-ingestion"])
_SUPPORTED_INGESTION_TYPES = set(get_ingestion_supported_file_types())


@admin_ingestion_router.post("/uploads/presign", response_model=PresignUploadResponse)
async def presign_upload(
    request: PresignUploadRequest,
    current_user: User = Depends(get_current_admin_user),
) -> PresignUploadResponse:
    _ = current_user
    if request.file_size and request.file_size > settings.max_upload_size:
        max_size_mb = settings.max_upload_size / (1024 * 1024)
        raise ValidationError(
            error_code="UPLOAD_FILE_TOO_LARGE",
            message=f"File size exceeds limit ({max_size_mb:.0f}MB)",
        )
    normalized_type = request.file_type.lower()
    if normalized_type not in _SUPPORTED_INGESTION_TYPES:
        raise ValidationError(
            error_code="INGESTION_INVALID_FILE_TYPE",
            message=f"Unsupported file type: {request.file_type}",
        )
    if not is_ingestion_file_type_supported(normalized_type):
        raise ValidationError(
            error_code="INGESTION_PARSER_UNAVAILABLE",
            message=f"Parser for file type {normalized_type} is not available in current runtime",
        )

    object_path = MinIOService.generate_object_path(request.file_name, request.file_type)
    upload_url = await MinIOService.generate_presigned_url(object_path)

    return PresignUploadResponse(upload_url=upload_url, object_path=object_path, expires_in=3600)


@admin_ingestion_router.post("/uploads/callback", response_model=UploadCallbackResponse)
async def upload_callback(
    request: UploadCallbackRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> UploadCallbackResponse:
    _ = current_user
    service = IngestionService(session, KnowledgePointRepository(session), IngestionJobRepository(session))
    job, kp = await service.create_upload_job(
        object_path=request.object_path,
        file_name=request.file_name,
        file_type=request.file_type,
        file_size=request.file_size,
    )

    return UploadCallbackResponse(
        job_id=job.id,
        status=job.status,
        message=f"Ingestion job created for knowledge point {kp.id}",
    )


@admin_ingestion_router.get("/knowledge-points", response_model=KnowledgePointListResponse)
async def list_knowledge_points(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    include_chunks: bool = False,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> KnowledgePointListResponse:
    _ = current_user
    kp_repo = KnowledgePointRepository(session)
    items, total = await kp_repo.list_knowledge_points(
        page=page,
        page_size=page_size,
        q=q,
        include_chunks=include_chunks,
    )

    return KnowledgePointListResponse(
        items=[KnowledgePointResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_ingestion_router.post("/knowledge-points", response_model=KnowledgePointResponse)
async def create_knowledge_point(
    request: KnowledgePointCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> KnowledgePointResponse:
    _ = current_user
    kp = await KnowledgePointRepository(session).create(
        title=request.title,
        file_type=request.file_type,
        object_path="",
        is_active=True,
    )
    return KnowledgePointResponse.model_validate(kp)


@admin_ingestion_router.get("/knowledge-points/{kp_id}", response_model=KnowledgePointResponse)
async def get_knowledge_point(
    kp_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> KnowledgePointResponse:
    _ = current_user
    kp = await KnowledgePointRepository(session).get_by_id(kp_id, include_chunks=True)
    if not kp:
        raise NotFoundError(error_code="KNOWLEDGE_POINT_NOT_FOUND", message="Knowledge point not found")
    return KnowledgePointResponse.model_validate(kp)


@admin_ingestion_router.delete("/knowledge-points/{kp_id}", response_model=KnowledgePointDeleteResponse)
async def delete_knowledge_point(
    kp_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> KnowledgePointDeleteResponse:
    service = IngestionService(session, KnowledgePointRepository(session), IngestionJobRepository(session))
    result = await service.delete_knowledge_point(kp_id, current_user.id)
    response = KnowledgePointDeleteResponse.model_validate(result)
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="knowledge_point.delete",
        resource_type="knowledge_point",
        resource_id=kp_id,
        summary="Deleted knowledge point and related chunks/jobs",
        metadata_json=response.model_dump(mode="json"),
    )
    return response


@admin_ingestion_router.get("/knowledge-points/{kp_id}/document-url", response_model=KnowledgePointDocumentUrlResponse)
async def get_knowledge_point_document_url(
    kp_id: UUID,
    expires_in: int = Query(default=3600, ge=60, le=86400),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> KnowledgePointDocumentUrlResponse:
    _ = current_user
    kp = await KnowledgePointRepository(session).get_by_id(kp_id, include_chunks=False)
    if not kp:
        raise NotFoundError(error_code="KNOWLEDGE_POINT_NOT_FOUND", message="Knowledge point not found")
    if not kp.object_path:
        raise ValidationError(error_code="KNOWLEDGE_POINT_NO_DOCUMENT", message="Knowledge point has no document")

    source_url = await MinIOService.get_file_url(
        kp.object_path,
        expires_in=expires_in,
        file_type=kp.file_type,
    )

    document_metadata = dict(getattr(kp, "document_metadata_json", {}) or {})
    preview_metadata = document_metadata.get("preview_artifact", {})
    if not isinstance(preview_metadata, dict):
        preview_metadata = {}

    preview_object_path_raw = str(preview_metadata.get("object_path") or "").strip()
    preview_object_path = preview_object_path_raw or None
    preview_file_type_raw = str(preview_metadata.get("file_type") or "").strip().lower()
    preview_file_type = preview_file_type_raw or None
    preview_available = bool(preview_metadata.get("available")) and bool(preview_object_path)
    preview_from_source = bool(preview_metadata.get("from_source")) or (
        bool(preview_object_path) and preview_object_path == kp.object_path
    )

    preview_url: str | None = None
    if preview_available and preview_object_path:
        if preview_object_path == kp.object_path:
            preview_url = source_url
            preview_from_source = True
            preview_file_type = preview_file_type or kp.file_type
        else:
            preview_url = await MinIOService.get_file_url(
                preview_object_path,
                expires_in=expires_in,
                file_type=preview_file_type,
            )
    elif kp.file_type.lower() == "pdf":
        preview_available = True
        preview_from_source = True
        preview_object_path = kp.object_path
        preview_file_type = kp.file_type
        preview_url = source_url
        preview_metadata = {
            "available": True,
            "from_source": True,
            "strategy": "source",
            "object_path": kp.object_path,
            "file_type": kp.file_type,
            "status": "ready",
            "message": None,
            "retrying": False,
        }

    preview_status = str(preview_metadata.get("status") or ("ready" if preview_available else "not_ready"))
    preview_message = str(preview_metadata.get("message") or "").strip() or None
    preview_error = str(preview_metadata.get("error") or "").strip() or None
    preview_retrying = bool(preview_metadata.get("retrying") or False)

    return KnowledgePointDocumentUrlResponse(
        url=source_url,
        object_path=kp.object_path,
        file_type=kp.file_type,
        expires_in=expires_in,
        source_url=source_url,
        source_object_path=kp.object_path,
        source_file_type=kp.file_type,
        preview_url=preview_url,
        preview_object_path=preview_object_path,
        preview_file_type=preview_file_type,
        preview_available=preview_available,
        preview_from_source=preview_from_source,
        preview_status=preview_status,
        preview_message=preview_message,
        preview_error=preview_error,
        preview_retrying=preview_retrying,
        preview_metadata=preview_metadata,
    )


@admin_ingestion_router.patch("/knowledge-points/{kp_id}", response_model=KnowledgePointResponse)
async def update_knowledge_point(
    kp_id: UUID,
    request: KnowledgePointUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> KnowledgePointResponse:
    _ = current_user
    kp = await KnowledgePointRepository(session).update(kp_id, **request.model_dump(exclude_unset=True))
    if not kp:
        raise NotFoundError(error_code="KNOWLEDGE_POINT_NOT_FOUND", message="Knowledge point not found")
    return KnowledgePointResponse.model_validate(kp)


@admin_ingestion_router.post("/knowledge-points/{kp_id}/reindex", response_model=IngestionJobResponse)
async def reindex_knowledge_point(
    kp_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> IngestionJobResponse:
    _ = current_user
    kp_repo = KnowledgePointRepository(session)
    job_repo = IngestionJobRepository(session)

    kp = await kp_repo.get_by_id(kp_id, include_chunks=False)
    if not kp:
        raise NotFoundError(error_code="KNOWLEDGE_POINT_NOT_FOUND", message="Knowledge point not found")

    if not kp.object_path:
        raise ValidationError(error_code="KNOWLEDGE_POINT_NO_FILE", message="Knowledge point has no file to reindex")
    normalized_type = kp.file_type.lower()
    if normalized_type not in _SUPPORTED_INGESTION_TYPES:
        raise ValidationError(
            error_code="INGESTION_INVALID_FILE_TYPE",
            message=f"Unsupported file type: {kp.file_type}",
        )
    if not is_ingestion_file_type_supported(normalized_type):
        raise ValidationError(
            error_code="INGESTION_PARSER_UNAVAILABLE",
            message=f"Parser for file type {normalized_type} is not available in current runtime",
        )
    try:
        object_stat = await MinIOService.stat_object(kp.object_path)
    except Exception as exc:
        raise ValidationError(
            error_code="INGESTION_OBJECT_NOT_FOUND",
            message=f"Uploaded object not found or inaccessible: {exc}",
        ) from exc
    if int(getattr(object_stat, "size", 0) or 0) <= 0:
        raise ValidationError(error_code="INGESTION_EMPTY_OBJECT", message="Uploaded object is empty")

    job = await job_repo.create(
        knowledge_point_id=kp.id,
        object_path=kp.object_path,
        file_type=normalized_type,
        status=JobStatus.PENDING,
        progress=0,
    )
    await session.commit()

    try:
        task = process_document.apply_async(args=[str(job.id)], task_id=f"reindex_{job.id}")
    except CeleryError as exc:
        await job_repo.update_status(
            job.id,
            status=JobStatus.FAILED,
            error_message=f"Failed to dispatch reindex task: {exc}",
        )
        await session.commit()
        raise ValidationError(
            error_code="INGESTION_TASK_DISPATCH_FAILED",
            message=f"Failed to dispatch reindex task: {exc}",
        ) from exc

    await job_repo.update_status(job.id, status=JobStatus.PENDING, celery_task_id=task.id)
    await session.commit()

    return IngestionJobResponse.model_validate(job)


@admin_ingestion_router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobResponse)
async def get_ingestion_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> IngestionJobResponse:
    _ = current_user
    job = await IngestionJobRepository(session).get_by_id(job_id)
    if not job:
        raise NotFoundError(error_code="INGESTION_JOB_NOT_FOUND", message="Ingestion job not found")
    IngestionService(session, KnowledgePointRepository(session), IngestionJobRepository(session)).log_if_job_stuck(job)
    return IngestionJobResponse.model_validate(job)


@admin_ingestion_router.get("/ingestion-jobs", response_model=IngestionJobListResponse)
async def list_ingestion_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: JobStatus | None = Query(default=None),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> IngestionJobListResponse:
    _ = current_user
    items, total = await IngestionJobRepository(session).list_jobs(
        page=page,
        page_size=page_size,
        status=status,
        q=q,
    )
    return IngestionJobListResponse(
        items=[IngestionJobResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_ingestion_router.post("/ingestion-jobs/{job_id}/retry", response_model=IngestionJobRetryResponse)
async def retry_ingestion_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_admin_user),
) -> IngestionJobRetryResponse:
    service = IngestionService(session, KnowledgePointRepository(session), IngestionJobRepository(session))
    original_job, new_job = await service.retry_failed_job(job_id, current_user.id)
    await AdminAuditService(session).record(
        actor_user_id=current_user.id,
        action="ingestion_job.retry",
        resource_type="ingestion_job",
        resource_id=job_id,
        summary="Retried failed ingestion job",
        metadata_json={"new_job_id": str(new_job.id)},
    )

    return IngestionJobRetryResponse(
        job_id=original_job.id,
        new_job_id=new_job.id,
        status=new_job.status,
        message="Retry job created successfully",
    )
