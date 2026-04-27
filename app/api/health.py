"""Health endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.core.config import (
    get_ingestion_supported_file_types,
    is_docling_pdf_runtime_available,
    is_docling_runtime_available,
)
from app.core.log_config import get_logger
from app.core.minio import check_minio
from app.core.redis import redis_client
from app.core.schema_guard import (
    ensure_database_schema_current,
    get_alembic_head_revisions,
    get_current_database_revision,
)
from app.models.engine import get_async_engine
from app.schemas import HealthResponse, ReadinessCheck, ReadinessResponse
from app.services.document_processing import get_document_runtime_readiness
from app.tasks.celery_app import check_celery_broker

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe: confirms process is alive without touching external dependencies."""
    return HealthResponse(status="ok", service="knowledge-base-agent")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """Readiness probe: validates PostgreSQL/Redis/MinIO/Celery broker availability."""
    checks: list[ReadinessCheck] = []
    all_healthy = True

    # 1) PostgreSQL
    try:
        async_engine = get_async_engine()
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks.append(ReadinessCheck(service="postgresql", status="ok"))
    except Exception as exc:
        checks.append(ReadinessCheck(service="postgresql", status="failed", message=str(exc)))
        all_healthy = False

    # 2) Redis
    try:
        await redis_client.ping()
        checks.append(ReadinessCheck(service="redis", status="ok"))
    except Exception as exc:
        checks.append(ReadinessCheck(service="redis", status="failed", message=str(exc)))
        all_healthy = False

    # 3) MinIO
    try:
        if await check_minio():
            checks.append(ReadinessCheck(service="minio", status="ok"))
        else:
            checks.append(
                ReadinessCheck(
                    service="minio",
                    status="failed",
                    message="MinIO connection failed",
                )
            )
            all_healthy = False
    except Exception as exc:
        checks.append(ReadinessCheck(service="minio", status="failed", message=str(exc)))
        all_healthy = False

    # 4) Celery broker
    try:
        if check_celery_broker():
            checks.append(ReadinessCheck(service="celery", status="ok"))
        else:
            checks.append(
                ReadinessCheck(
                    service="celery",
                    status="failed",
                    message="Celery broker connection failed",
                )
            )
            all_healthy = False
    except Exception as exc:
        checks.append(ReadinessCheck(service="celery", status="failed", message=str(exc)))
        all_healthy = False

    # 5) Database schema revision
    try:
        current_revision = await get_current_database_revision()
        head_revisions = get_alembic_head_revisions()
        try:
            await ensure_database_schema_current()
            checks.append(
                ReadinessCheck(
                    service="database_schema",
                    status="ok",
                    message=f"revision={current_revision or '<none>'}",
                )
            )
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    service="database_schema",
                    status="failed",
                    message=(
                        f"{exc} "
                        f"(current={current_revision or '<none>'}, expected={','.join(head_revisions) or '<none>'})"
                    ),
                )
            )
            all_healthy = False
    except Exception as exc:
        checks.append(ReadinessCheck(service="database_schema", status="failed", message=str(exc)))
        all_healthy = False

    # 6) Document parser capability
    try:
        allowed_types = list(get_ingestion_supported_file_types())
        readiness = get_document_runtime_readiness(allowed_types)
        missing_types = list(readiness.get("missing_types") or [])
        docling_runtime_ready = is_docling_runtime_available()
        docling_pdf_runtime_ready = is_docling_pdf_runtime_available()
        readiness_message = {
            key: value
            for key, value in readiness.items()
            if key not in {"converter_doc_ready", "converter_ppt_ready", "docling_parser_ready"}
        }
        readiness_message.update(
            {
                "docling_runtime_ready": docling_runtime_ready,
                "docling_pdf_runtime_ready": docling_pdf_runtime_ready,
                "supported_file_types": allowed_types,
                "legacy_file_types_blocked": ["doc", "ppt"],
            }
        )

        if missing_types or not docling_runtime_ready:
            checks.append(
                ReadinessCheck(
                    service="document_parsers",
                    status="failed",
                    message=json.dumps(readiness_message, ensure_ascii=False),
                )
            )
            all_healthy = False
        else:
            checks.append(
                ReadinessCheck(
                    service="document_parsers",
                    status="ok",
                    message=json.dumps(readiness_message, ensure_ascii=False),
                )
            )
    except Exception as exc:
        checks.append(ReadinessCheck(service="document_parsers", status="failed", message=str(exc)))
        all_healthy = False

    readiness_status = "ready" if all_healthy else "not_ready"
    payload = ReadinessResponse(status=readiness_status, checks=checks)

    if not all_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=payload.model_dump(),
        )

    return payload
