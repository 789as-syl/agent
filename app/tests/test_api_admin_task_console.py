from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.ingestion_job import IngestionJob
from app.models.vectorization_job import VectorizationJob


@pytest.mark.asyncio
async def test_admin_task_console_merges_ingestion_and_vectorization_jobs(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    db_session.add(IngestionJob(object_path="documents/a.pdf", file_type="pdf", status=JobStatus.FAILED, progress=10))
    db_session.add(VectorizationJob(status=JobStatus.PENDING, progress=0, total_questions=3, processed_questions=0))
    await db_session.commit()

    denied = await client.get("/api/v1/admin/tasks", headers=auth_headers)
    assert denied.status_code == 403

    response = await client.get("/api/v1/admin/tasks", headers=admin_auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 2
    assert {item["task_type"] for item in payload["items"]} >= {"ingestion", "vectorization"}
    assert payload["summary"]["failed_ingestion_jobs"] >= 1


@pytest.mark.asyncio
async def test_admin_quality_radar_reports_warnings(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    db_session.add(IngestionJob(object_path="documents/failed.pdf", file_type="pdf", status=JobStatus.FAILED, progress=30))
    await db_session.commit()

    response = await client.get("/api/v1/admin/quality-radar", headers=admin_auth_headers)
    assert response.status_code == 200
    assert response.json()["failed_ingestion_jobs"] >= 1
    assert any(item["code"] == "FAILED_INGESTION_JOBS" for item in response.json()["warnings"])
