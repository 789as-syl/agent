"""Asynchronous ingestion tasks for knowledge-point document processing."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.embedding_utils import generate_dashscope_embeddings, is_retryable_task_exception
from app.core.file_signature import detect_file_type
from app.core.log_config import get_logger
from app.core.minio import minio_client
from app.models.engine import get_celery_session, init_db_engine
from app.models.enums import JobStatus
from app.repositories.ingestion_job_repo import IngestionJobRepository
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.services.document_processing import (
    CHUNKER_VERSION,
    CLEANING_PROFILE_ID,
    PARSER_VERSION,
    ChunkBuildResult,
    DoclingDocument,
    build_chunk_bundle,
    build_preview_html_artifact,
    is_generated_preview_supported,
    parse_document_artifact,
)
from app.services.minio_service import MinIOService
from app.tasks.async_runner import run_coroutine_sync

logger = get_logger(__name__)

SAFE_FILE_EXTENSIONS = {"pdf", "md", "docx", "html", "pptx", "txt"}


def _run_async(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    """Run coroutine in dedicated async runner loop."""
    return cast(dict[str, Any], run_coroutine_sync(coro))


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion_tasks.process_document",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_document(self: Any, job_id_str: str) -> dict[str, Any]:
    """Process uploaded document into cleaned, chunked, embedded knowledge chunks."""
    job_id = UUID(job_id_str)
    init_db_engine()

    async def run_ingestion() -> dict[str, Any]:
        async with get_celery_session() as session:
            job_repo = IngestionJobRepository(session)
            kp_repo = KnowledgePointRepository(session)
            current_progress = 0

            existing_job = await job_repo.get_by_id(job_id)
            if existing_job and existing_job.status == JobStatus.SUCCESS:
                logger.info("Ingestion job already completed, skipping", job_id=str(job_id))
                return {"status": "success", "chunks": 0, "skipped": True}
            if (
                existing_job
                and existing_job.status == JobStatus.FAILED
                and existing_job.knowledge_point_id is None
            ):
                logger.info(
                    "Ingestion job detached from knowledge point, skipping",
                    job_id=str(job_id),
                    object_path=existing_job.object_path,
                )
                return {
                    "status": "failed",
                    "chunks": 0,
                    "skipped": True,
                    "reason": "knowledge_point_deleted",
                }

            try:
                await job_repo.update_status(job_id, status=JobStatus.RUNNING, progress=10)
                current_progress = 10
                job = await job_repo.get_by_id(job_id)
                if not job:
                    raise ValueError(f"Job {job_id} not found")

                await job_repo.update_status(job_id, progress=20)
                current_progress = 20
                tmp_file_path = await download_from_minio_async(
                    bucket_name=settings.minio_bucket_name,
                    object_path=job.object_path,
                    suffix=Path(job.object_path).suffix or f".{job.file_type}",
                    expected_file_type=job.file_type,
                )

                try:
                    await job_repo.update_status(job_id, progress=40)
                    current_progress = 40
                    document = parse_document(tmp_file_path, job.file_type)
                    if not getattr(document, "blocks", None):
                        raise ValueError("Document parser returned no textual content")

                    await job_repo.update_status(job_id, progress=55)
                    current_progress = 55
                    chunk_bundle = build_chunks(job.file_type, document)
                    if isinstance(chunk_bundle, list):
                        chunk_payloads = list(chunk_bundle)
                        chunk_bundle = ChunkBuildResult(chunks=chunk_payloads, document_metadata={})
                    else:
                        chunk_payloads = list(chunk_bundle.chunks)
                    if not chunk_payloads:
                        raise ValueError("Document produced no chunks after cleaning and splitting")

                    logger.info(
                        "Document chunking completed",
                        job_id=str(job_id),
                        section_count=len(document.blocks),
                        chunk_count=len(chunk_payloads),
                        parser_name=document.parser_name,
                        quality_status=chunk_bundle.document_metadata.get("quality_status"),
                    )

                    preview_metadata = await _generate_preview_metadata(
                        source_object_path=job.object_path,
                        source_file_type=job.file_type,
                        document=document,
                    )
                    docling_artifact_metadata = await _generate_docling_artifact_metadata(
                        source_object_path=job.object_path,
                        source_file_type=job.file_type,
                        document=document,
                    )
                    truth_signature = _build_truth_signature_metadata(
                        source_object_path=job.object_path,
                        source_file_type=job.file_type,
                        document=document,
                        chunk_bundle=chunk_bundle,
                        chunk_count=len(chunk_payloads),
                        preview_metadata=preview_metadata,
                        docling_artifact_metadata=docling_artifact_metadata,
                    )

                    await job_repo.update_status(job_id, progress=70)
                    current_progress = 70
                    embedding_inputs = [str(item.pop("embedding_input", item["content"])) for item in chunk_payloads]
                    embeddings = await generate_embeddings_batch(embedding_inputs)

                    for payload, embedding in zip(chunk_payloads, embeddings, strict=True):
                        payload["embedding"] = embedding

                    await job_repo.update_status(job_id, progress=85)
                    current_progress = 85
                    if job.knowledge_point_id is None:
                        raise ValueError(f"Job {job_id} is missing knowledge_point_id")
                    kp = await kp_repo.get_by_id(job.knowledge_point_id, include_chunks=False)
                    if not kp:
                        raise ValueError(f"Knowledge point {job.knowledge_point_id} not found")
                    existing_document_metadata = dict(getattr(kp, "document_metadata_json", {}) or {})
                    merged_document_metadata = _merge_document_metadata(
                        existing_metadata=existing_document_metadata,
                        chunk_metadata=chunk_bundle.document_metadata,
                        preview_metadata=preview_metadata,
                        docling_artifact_metadata=docling_artifact_metadata,
                        truth_signature=truth_signature,
                    )
                    await kp_repo.delete_chunks_by_kp_id(job.knowledge_point_id)
                    await kp_repo.update(
                        job.knowledge_point_id,
                        document_metadata_json=merged_document_metadata,
                    )
                    await kp_repo.create_chunks(job.knowledge_point_id, chunk_payloads)

                    await job_repo.update_status(job_id, status=JobStatus.SUCCESS, progress=100, error_message=None)
                    current_progress = 100
                    logger.info(
                        "Ingestion job completed",
                        job_id=str(job_id),
                        knowledge_point_id=str(job.knowledge_point_id),
                        chunk_count=len(chunk_payloads),
                    )
                    return {"status": "success", "chunks": len(chunk_payloads)}
                finally:
                    await cleanup_temp_file(tmp_file_path)
            except Exception as exc:
                logger.error("Ingestion job failed", job_id=str(job_id), error=str(exc), exc_info=True)
                retryable = self.request.retries < self.max_retries and is_retryable_task_exception(exc)
                await _persist_ingestion_job_status(
                    session,
                    job_id,
                    status=JobStatus.PENDING if retryable else JobStatus.FAILED,
                    progress=min(current_progress, 99) if current_progress else 0,
                    error_message=str(exc),
                )
                if retryable:
                    raise self.retry(exc=exc, countdown=60 * (2**self.request.retries)) from exc
                raise

    return _run_async(run_ingestion())


async def _persist_ingestion_job_status(
    session: AsyncSession,
    job_id: UUID,
    *,
    status: JobStatus,
    progress: int,
    error_message: str | None,
) -> None:
    """Persist ingestion job state after rolling back any failed work."""
    try:
        await session.rollback()
        await IngestionJobRepository(session).update_status(
            job_id,
            status=status,
            progress=progress,
            error_message=error_message,
        )
        await session.commit()
    except Exception as persist_exc:  # pragma: no cover - defensive persistence logging
        logger.error(
            "Failed to persist ingestion job state",
            job_id=str(job_id),
            status=status.value,
            error=str(persist_exc),
            exc_info=True,
        )


async def download_from_minio_async(bucket_name: str, object_path: str, suffix: str, expected_file_type: str) -> str:
    """Download object from MinIO into a temporary file and validate its signature."""

    def _sync_download() -> str:
        response = minio_client.get_object(bucket_name, object_path)
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                for chunk in response.stream(amt=1024 * 1024):
                    tmp_file.write(chunk)
                return tmp_file.name
        finally:
            response.close()
            response.release_conn()

    file_path = await asyncio.to_thread(_sync_download)

    with open(file_path, "rb") as file_handle:
        header = file_handle.read(8192)

    expected_type = expected_file_type.lower()
    detected_type = detect_file_type(header)
    zip_match = detected_type == "docx" and expected_type in {"docx", "pptx"}
    if detected_type and detected_type != expected_type and not zip_match:
        os.unlink(file_path)
        raise ValueError(
            f"File type mismatch: expected {expected_file_type}, but detected {detected_type}. "
            "The uploaded file may be corrupted or mislabeled."
        )

    if detected_type is None and expected_file_type.lower() in SAFE_FILE_EXTENSIONS:
        logger.warning(
            "Could not verify file signature; proceeding with declared type",
            object_path=object_path,
            expected_file_type=expected_file_type,
        )

    return file_path


async def cleanup_temp_file(file_path: str) -> None:
    """Delete temporary file and ignore cleanup failures."""
    try:
        await asyncio.to_thread(Path(file_path).unlink, missing_ok=True)
    except Exception as exc:  # pragma: no cover - defensive cleanup
        logger.warning("Failed to cleanup temp file", file_path=file_path, error=str(exc))


async def generate_embeddings_batch(texts: list[str], batch_size: int | None = None) -> list[list[float]]:
    """Generate embeddings in batches using the DashScope batch API when available."""
    return await generate_dashscope_embeddings(
        texts,
        model_name=settings.retrieval_embedding_model,
        api_key=settings.dashscope_api_key,
        batch_size=batch_size or settings.retrieval_embedding_batch_size,
        text_type="document",
        expected_dimension=settings.retrieval_embedding_dimension,
    )


def parse_document(file_path: str, file_type: str) -> DoclingDocument:
    """Parse a document into the normalized upstream Docling-derived artifact."""
    return parse_document_artifact(file_path, file_type)


def build_chunks(file_type: str, document: DoclingDocument) -> ChunkBuildResult:
    """Build contextualized chunk payloads and document-level quality metadata."""
    return build_chunk_bundle(file_type=file_type, document=document)


async def _generate_preview_metadata(
    *,
    source_object_path: str,
    source_file_type: str,
    document: DoclingDocument,
) -> dict[str, Any]:
    normalized_type = str(source_file_type or "").lower()
    generated_at = datetime.now(UTC).isoformat()

    if normalized_type == "pdf":
        return {
            "available": True,
            "from_source": True,
            "strategy": "source",
            "status": "ready",
            "message": None,
            "error": None,
            "retrying": False,
            "object_path": source_object_path,
            "file_type": normalized_type,
            "content_type": "application/pdf",
            "generated_at": generated_at,
        }

    if is_generated_preview_supported(normalized_type):
        preview_html = build_preview_html_artifact(document=document)
        preview_object_path = MinIOService.generate_preview_object_path(
            source_object_path,
            preview_file_type="html",
        )
        await MinIOService.upload_preview_artifact(
            preview_object_path,
            preview_html.encode("utf-8"),
            content_type="text/html; charset=utf-8",
            metadata={
                "source_object_path": source_object_path,
                "source_file_type": normalized_type,
            },
        )
        return {
            "available": True,
            "from_source": False,
            "strategy": "generated_html",
            "status": "ready",
            "message": None,
            "error": None,
            "retrying": False,
            "object_path": preview_object_path,
            "file_type": "html",
            "content_type": "text/html; charset=utf-8",
            "generated_at": generated_at,
            "source_file_type": normalized_type,
            "source_object_path": source_object_path,
            "preview_char_count": len(preview_html),
        }

    return {
        "available": False,
        "from_source": False,
        "strategy": "unsupported",
        "status": "not_ready",
        "message": "当前文件类型暂不提供内嵌预览，已回退到源文件地址。",
        "error": None,
        "retrying": False,
        "object_path": None,
        "file_type": None,
        "content_type": None,
        "generated_at": generated_at,
        "source_file_type": normalized_type,
        "source_object_path": source_object_path,
    }


async def _generate_docling_artifact_metadata(
    *,
    source_object_path: str,
    source_file_type: str,
    document: DoclingDocument,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    cache_path = Path(str(document.cache_path or ""))
    if not document.cache_path or not cache_path.exists():
        return {
            "available": False,
            "status": "not_ready",
            "object_path": None,
            "cache_path": str(document.cache_path or ""),
            "generated_at": generated_at,
            "source_object_path": source_object_path,
            "source_file_type": str(source_file_type or "").lower(),
        }

    artifact_object_path = MinIOService.generate_docling_artifact_object_path(source_object_path)
    payload = cache_path.read_bytes()
    await MinIOService.upload_preview_artifact(
        artifact_object_path,
        payload,
        content_type="application/json; charset=utf-8",
        metadata={
            "artifact_kind": "docling_json",
            "source_object_path": source_object_path,
            "source_file_type": str(source_file_type or "").lower(),
        },
    )
    return {
        "available": True,
        "status": "ready",
        "object_path": artifact_object_path,
        "cache_path": str(document.cache_path or ""),
        "generated_at": generated_at,
        "source_object_path": source_object_path,
        "source_file_type": str(source_file_type or "").lower(),
    }


def _build_truth_signature_metadata(
    *,
    source_object_path: str,
    source_file_type: str,
    document: DoclingDocument,
    chunk_bundle: ChunkBuildResult,
    chunk_count: int,
    preview_metadata: dict[str, Any],
    docling_artifact_metadata: dict[str, Any],
) -> dict[str, Any]:
    parser_meta = {
        "name": document.parser_name,
        "version": PARSER_VERSION,
        "ocr_used": document.ocr_used,
        "quality_status": chunk_bundle.document_metadata.get("quality_status"),
    }
    chunker_meta = {
        "name": "hybrid_chunk_bundle",
        "version": CHUNKER_VERSION,
        "chunk_count": chunk_count,
        "avg_chunk_chars": chunk_bundle.document_metadata.get("avg_chunk_chars"),
        "short_chunk_ratio": chunk_bundle.document_metadata.get("short_chunk_ratio"),
        "duplicate_chunk_ratio": chunk_bundle.document_metadata.get("duplicate_chunk_ratio"),
    }
    profile_meta = {
        "name": CLEANING_PROFILE_ID,
        "generated_preview_supported": is_generated_preview_supported(source_file_type),
        "preview_strategy": preview_metadata.get("strategy"),
    }
    source_meta = {
        "object_path": source_object_path,
        "file_type": str(source_file_type or "").lower(),
        "content_hash": document.content_hash,
        "cache_path": document.cache_path,
        "artifact_object_path": docling_artifact_metadata.get("object_path"),
        "extracted_char_count": document.extracted_char_count,
    }

    base_payload = {
        "version": "v1",
        "parser": parser_meta,
        "chunker": chunker_meta,
        "profile": profile_meta,
        "source": source_meta,
    }
    return {
        **base_payload,
        "parser_signature": _compute_signature(parser_meta),
        "chunker_signature": _compute_signature(chunker_meta),
        "profile_signature": _compute_signature(profile_meta),
        "source_signature": _compute_signature(source_meta),
        "signature": _compute_signature(base_payload),
    }


def _merge_document_metadata(
    *,
    existing_metadata: dict[str, Any],
    chunk_metadata: dict[str, Any],
    preview_metadata: dict[str, Any],
    docling_artifact_metadata: dict[str, Any],
    truth_signature: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing_metadata or {})
    merged.update(chunk_metadata or {})
    merged["preview_artifact"] = preview_metadata
    merged["docling_artifact"] = docling_artifact_metadata
    merged["truth_signature"] = truth_signature
    merged["metadata_updated_at"] = datetime.now(UTC).isoformat()
    return merged


def _compute_signature(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
