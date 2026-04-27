"""Tests for ingestion admin APIs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.ingestion_job import IngestionJob
from app.models.knowledge_point import KnowledgePoint, KnowledgePointChunk


@pytest.fixture
def patch_ingestion_dependencies(
    monkeypatch: MonkeyPatch,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    redis_mock = SimpleNamespace(set=AsyncMock(return_value=True), delete=AsyncMock(return_value=1))
    monkeypatch.setattr("app.services.ingestion_service.redis_client", redis_mock)

    task_stub = SimpleNamespace(apply_async=MagicMock(return_value=SimpleNamespace(id="ingestion-task-id")))
    monkeypatch.setattr("app.services.ingestion_service.process_document", task_stub)
    return redis_mock, task_stub


class TestPresignAndCallback:
    @pytest.mark.asyncio
    async def test_presign_supports_mime_file_type(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        monkeypatch: MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.api.ingestion.is_ingestion_file_type_supported", lambda _: True)
        monkeypatch.setattr(
            "app.services.minio_service.MinIOService.generate_presigned_url",
            AsyncMock(return_value="http://minio.local/upload"),
        )

        response = await client.post(
            "/api/v1/admin/uploads/presign",
            headers=admin_auth_headers,
            json={
                "file_name": "test.pdf",
                "file_type": "application/pdf",
                "file_size": 1024,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["upload_url"] == "http://minio.local/upload"
        assert payload["expires_in"] == 3600

    @pytest.mark.asyncio
    async def test_upload_callback_supports_mime_file_type(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        patch_ingestion_dependencies: tuple[SimpleNamespace, SimpleNamespace],
        monkeypatch: MonkeyPatch,
    ) -> None:
        _ = patch_ingestion_dependencies
        object_name = f"documents/{uuid4()}.pdf"
        monkeypatch.setattr("app.services.ingestion_service.is_ingestion_file_type_supported", lambda _: True)
        monkeypatch.setattr(
            "app.services.minio_service.MinIOService.stat_object",
            AsyncMock(return_value=SimpleNamespace(size=2048)),
        )
        response = await client.post(
            "/api/v1/admin/uploads/callback",
            headers=admin_auth_headers,
            json={
                "object_path": object_name,
                "file_name": "test-probe.pdf",
                "file_type": "application/pdf",
                "file_size": 2048,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "pending"
        assert payload["job_id"]


class TestKnowledgePointListFilters:
    @pytest.mark.asyncio
    async def test_list_knowledge_points_supports_q_and_include_chunks(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        kp_python = KnowledgePoint(
            id=uuid4(),
            title="Python Basics",
            file_type="pdf",
            object_path="documents/python.pdf",
            is_active=True,
        )
        kp_math = KnowledgePoint(
            id=uuid4(),
            title="Math Basics",
            file_type="pdf",
            object_path="documents/math.pdf",
            is_active=True,
        )
        db_session.add_all([kp_python, kp_math])
        await db_session.flush()

        chunk = KnowledgePointChunk(
            id=uuid4(),
            knowledge_point_id=kp_python.id,
            chunk_index=0,
            content="Python chunk",
            metadata_json={"source": "test"},
        )
        db_session.add(chunk)
        await db_session.flush()

        resp_without_chunks = await client.get(
            "/api/v1/admin/knowledge-points?q=Python&include_chunks=false",
            headers=admin_auth_headers,
        )
        assert resp_without_chunks.status_code == 200
        payload_without = resp_without_chunks.json()
        assert payload_without["total"] == 1
        assert payload_without["items"][0]["title"] == "Python Basics"

        resp_with_chunks = await client.get(
            "/api/v1/admin/knowledge-points?q=Python&include_chunks=true",
            headers=admin_auth_headers,
        )
        assert resp_with_chunks.status_code == 200
        payload_with = resp_with_chunks.json()
        assert payload_with["total"] == 1
        assert len(payload_with["items"][0]["chunks"]) == 1

    @pytest.mark.asyncio
    async def test_get_knowledge_point_document_url(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        monkeypatch: MonkeyPatch,
    ) -> None:
        kp = KnowledgePoint(
            id=uuid4(),
            title="Preview Doc",
            file_type="pdf",
            object_path="documents/preview.pdf",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        monkeypatch.setattr(
            "app.services.minio_service.MinIOService.get_file_url",
            AsyncMock(return_value="http://minio.local/preview"),
        )

        response = await client.get(
            f"/api/v1/admin/knowledge-points/{kp.id}/document-url?expires_in=3600",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["url"] == "http://minio.local/preview"
        assert payload["source_url"] == "http://minio.local/preview"
        assert payload["object_path"] == "documents/preview.pdf"
        assert payload["source_object_path"] == "documents/preview.pdf"
        assert payload["file_type"] == "pdf"
        assert payload["source_file_type"] == "pdf"
        assert payload["preview_url"] == "http://minio.local/preview"
        assert payload["preview_object_path"] == "documents/preview.pdf"
        assert payload["preview_file_type"] == "pdf"
        assert payload["preview_available"] is True
        assert payload["preview_from_source"] is True
        assert payload["preview_status"] == "ready"
        assert payload["preview_retrying"] is False
        assert payload["expires_in"] == 3600

    @pytest.mark.asyncio
    async def test_get_knowledge_point_document_url_passes_file_type_for_inline_preview(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        monkeypatch: MonkeyPatch,
    ) -> None:
        kp = KnowledgePoint(
            id=uuid4(),
            title="Markdown Preview",
            file_type="md",
            object_path="documents/preview.md",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        captured_args: dict[str, object] = {}

        async def _fake_get_file_url(object_path: str, expires_in: int = 3600, *, file_type: str | None = None) -> str:
            captured_args.update(
                {
                    "object_path": object_path,
                    "expires_in": expires_in,
                    "file_type": file_type,
                }
            )
            return "http://minio.local/preview-md"

        monkeypatch.setattr("app.services.minio_service.MinIOService.get_file_url", _fake_get_file_url)

        response = await client.get(
            f"/api/v1/admin/knowledge-points/{kp.id}/document-url?expires_in=600",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert captured_args == {
            "object_path": "documents/preview.md",
            "expires_in": 600,
            "file_type": "md",
        }
        payload = response.json()
        assert payload["url"] == "http://minio.local/preview-md"
        assert payload["source_url"] == "http://minio.local/preview-md"
        assert payload["source_object_path"] == "documents/preview.md"
        assert payload["source_file_type"] == "md"
        assert payload["preview_status"] == "not_ready"
        assert payload["preview_available"] is False

    @pytest.mark.asyncio
    async def test_get_knowledge_point_document_url_prefers_generated_preview_artifact(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        monkeypatch: MonkeyPatch,
    ) -> None:
        kp = KnowledgePoint(
            id=uuid4(),
            title="Slides Preview",
            file_type="pptx",
            object_path="documents/slides.pptx",
            is_active=True,
            document_metadata_json={
                "preview_artifact": {
                    "available": True,
                    "from_source": False,
                    "strategy": "generated_html",
                    "status": "ready",
                    "retrying": False,
                    "object_path": "previews/slides.preview.html",
                    "file_type": "html",
                }
            },
        )
        db_session.add(kp)
        await db_session.flush()

        captured_calls: list[dict[str, object]] = []

        async def _fake_get_file_url(object_path: str, expires_in: int = 3600, *, file_type: str | None = None) -> str:
            captured_calls.append(
                {
                    "object_path": object_path,
                    "expires_in": expires_in,
                    "file_type": file_type,
                }
            )
            return f"http://minio.local/{object_path.replace('/', '_')}"

        monkeypatch.setattr("app.services.minio_service.MinIOService.get_file_url", _fake_get_file_url)

        response = await client.get(
            f"/api/v1/admin/knowledge-points/{kp.id}/document-url?expires_in=900",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert captured_calls == [
            {
                "object_path": "documents/slides.pptx",
                "expires_in": 900,
                "file_type": "pptx",
            },
            {
                "object_path": "previews/slides.preview.html",
                "expires_in": 900,
                "file_type": "html",
            },
        ]
        payload = response.json()
        assert payload["source_url"] == "http://minio.local/documents_slides.pptx"
        assert payload["preview_url"] == "http://minio.local/previews_slides.preview.html"
        assert payload["preview_file_type"] == "html"
        assert payload["preview_available"] is True
        assert payload["preview_from_source"] is False

    @pytest.mark.asyncio
    async def test_get_knowledge_point_document_url_requires_object_path(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        kp = KnowledgePoint(
            id=uuid4(),
            title="No Doc",
            file_type="pdf",
            object_path="",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        response = await client.get(
            f"/api/v1/admin/knowledge-points/{kp.id}/document-url",
            headers=admin_auth_headers,
        )
        assert response.status_code == 422


class TestIngestionJobs:
    @pytest.mark.asyncio
    async def test_get_ingestion_job_not_found(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        response = await client.get(
            f"/api/v1/admin/ingestion-jobs/{uuid4()}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_non_failed_job_should_fail(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        from app.models.ingestion_job import IngestionJob

        kp = KnowledgePoint(
            id=uuid4(),
            title="KP",
            file_type="pdf",
            object_path="documents/file.pdf",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        job = IngestionJob(
            id=uuid4(),
            knowledge_point_id=kp.id,
            object_path=kp.object_path,
            file_type=kp.file_type,
            status=JobStatus.SUCCESS,
            progress=100,
        )
        db_session.add(job)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/admin/ingestion-jobs/{job.id}/retry",
            headers=admin_auth_headers,
        )
        assert response.status_code == 422


class TestKnowledgePointDeletion:
    @pytest.mark.asyncio
    async def test_delete_knowledge_point_cascades_related_data(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        monkeypatch: MonkeyPatch,
    ) -> None:
        delete_object_mock = AsyncMock(return_value=None)
        revoke_mock = MagicMock()

        monkeypatch.setattr("app.services.minio_service.MinIOService.delete_object", delete_object_mock)
        monkeypatch.setattr(
            "app.services.ingestion_service.celery_app",
            SimpleNamespace(control=SimpleNamespace(revoke=revoke_mock)),
        )

        kp = KnowledgePoint(
            id=uuid4(),
            title="Python Basics",
            file_type="pdf",
            object_path="documents/python.pdf",
            is_active=True,
        )
        db_session.add(kp)
        await db_session.flush()

        db_session.add(
            KnowledgePointChunk(
                id=uuid4(),
                knowledge_point_id=kp.id,
                chunk_index=0,
                content="chunk body",
                metadata_json={"page": 1},
            )
        )

        success_job = IngestionJob(
            id=uuid4(),
            knowledge_point_id=kp.id,
            object_path=kp.object_path,
            file_type=kp.file_type,
            status=JobStatus.SUCCESS,
            progress=100,
        )
        running_job = IngestionJob(
            id=uuid4(),
            knowledge_point_id=kp.id,
            object_path=kp.object_path,
            file_type=kp.file_type,
            status=JobStatus.RUNNING,
            progress=55,
            celery_task_id="celery-running-task",
        )
        db_session.add_all([success_job, running_job])
        await db_session.flush()

        response = await client.delete(
            f"/api/v1/admin/knowledge-points/{kp.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["knowledge_point_id"] == str(kp.id)
        assert payload["deleted_chunk_count"] == 1
        assert payload["detached_job_count"] == 2
        assert payload["revoked_task_count"] == 1
        assert payload["object_deleted"] is True
        assert payload["message"] == "Knowledge point deleted successfully"

        delete_object_mock.assert_awaited_once_with("documents/python.pdf")
        revoke_mock.assert_called_once_with("celery-running-task", terminate=False)

        deleted_kp = await db_session.get(KnowledgePoint, kp.id)
        assert deleted_kp is None

        remaining_chunks = (
            await db_session.execute(
                select(KnowledgePointChunk).where(KnowledgePointChunk.knowledge_point_id == kp.id)
            )
        ).scalars().all()
        assert remaining_chunks == []

        persisted_success_job = await db_session.get(IngestionJob, success_job.id)
        assert persisted_success_job is not None
        assert persisted_success_job.knowledge_point_id is None
        assert persisted_success_job.status == JobStatus.SUCCESS

        persisted_running_job = await db_session.get(IngestionJob, running_job.id)
        assert persisted_running_job is not None
        assert persisted_running_job.knowledge_point_id is None
        assert persisted_running_job.status == JobStatus.FAILED
        assert persisted_running_job.error_message == "Knowledge point deleted by admin"

    @pytest.mark.asyncio
    async def test_delete_knowledge_point_not_found(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        response = await client.delete(
            f"/api/v1/admin/knowledge-points/{uuid4()}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404
