"""Unit tests for ingestion tasks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.core.embedding_utils import EmbeddingProviderError
from app.models.enums import JobStatus
from app.tasks import ingestion_tasks


class _AsyncSessionContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _run_immediately(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def test_generate_embeddings_batch_surfaces_provider_error(monkeypatch):
    async def _fake_generate_embeddings(*args, **kwargs):
        raise EmbeddingProviderError(
            "DashScope embedding request failed (status=400, code=Arrearage): account overdue",
            retryable=False,
            status_code=400,
            code="Arrearage",
        )

    monkeypatch.setattr(ingestion_tasks, "generate_dashscope_embeddings", _fake_generate_embeddings)

    with pytest.raises(EmbeddingProviderError, match="Arrearage"):
        _run_immediately(ingestion_tasks.generate_embeddings_batch(["知识块 A"]))


def test_persist_ingestion_job_status_rolls_back_then_commits(monkeypatch):
    job_id = uuid4()
    events: list[object] = []

    async def _rollback():
        events.append("rollback")

    async def _commit():
        events.append("commit")

    session = SimpleNamespace(rollback=_rollback, commit=_commit)

    class _FakeJobRepo:
        def __init__(self, incoming_session):
            assert incoming_session is session

        async def update_status(self, incoming_job_id: UUID, **kwargs):
            assert incoming_job_id == job_id
            events.append(("update_status", kwargs))
            return None

    monkeypatch.setattr(ingestion_tasks, "IngestionJobRepository", _FakeJobRepo)

    _run_immediately(
        ingestion_tasks._persist_ingestion_job_status(
            session,
            job_id,
            status=JobStatus.FAILED,
            progress=70,
            error_message="embedding failed",
        )
    )

    assert events == [
        "rollback",
        (
            "update_status",
            {
                "status": JobStatus.FAILED,
                "progress": 70,
                "error_message": "embedding failed",
            },
        ),
        "commit",
    ]


def test_process_document_marks_permanent_embedding_failure_without_retry(monkeypatch):
    job_id = uuid4()
    knowledge_point_id = uuid4()
    persisted_states: list[dict] = []
    retry_calls: list[dict] = []
    cleanup_mock = AsyncMock(return_value=None)

    job = SimpleNamespace(
        id=job_id,
        status=JobStatus.PENDING,
        object_path="documents/test.pdf",
        file_type="pdf",
        knowledge_point_id=knowledge_point_id,
    )

    class _FakeJobRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, incoming_job_id: UUID):
            assert incoming_job_id == job_id
            return job

        async def update_status(self, incoming_job_id: UUID, **kwargs):
            assert incoming_job_id == job_id
            if "status" in kwargs and kwargs["status"] is not None:
                job.status = kwargs["status"]
            return job

    class _FakeKnowledgePointRepo:
        def __init__(self, session):
            self.session = session

        async def delete_chunks_by_kp_id(self, kp_id: UUID):
            raise AssertionError("delete_chunks_by_kp_id should not be called after embedding failure")

        async def create_chunks(self, kp_id: UUID, payloads: list[dict]):
            raise AssertionError("create_chunks should not be called after embedding failure")

    async def _fake_generate_embeddings(texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        raise EmbeddingProviderError(
            "DashScope embedding request failed (status=400, code=Arrearage): account overdue",
            retryable=False,
            status_code=400,
            code="Arrearage",
        )

    async def _fake_persist_status(session, incoming_job_id: UUID, **kwargs):
        persisted_states.append({"job_id": incoming_job_id, **kwargs})

    def _unexpected_retry(*args, **kwargs):
        retry_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("retry should not be called for permanent embedding failures")

    monkeypatch.setattr(ingestion_tasks, "init_db_engine", lambda: None)
    monkeypatch.setattr(ingestion_tasks, "_run_async", _run_immediately)
    monkeypatch.setattr(ingestion_tasks, "get_celery_session", lambda: _AsyncSessionContext(object()))
    monkeypatch.setattr(ingestion_tasks, "IngestionJobRepository", _FakeJobRepo)
    monkeypatch.setattr(ingestion_tasks, "KnowledgePointRepository", _FakeKnowledgePointRepo)
    monkeypatch.setattr(ingestion_tasks, "download_from_minio_async", AsyncMock(return_value="tmp-file.pdf"))
    monkeypatch.setattr(ingestion_tasks, "cleanup_temp_file", cleanup_mock)
    monkeypatch.setattr(
        ingestion_tasks,
        "parse_document",
        lambda *_args, **_kwargs: SimpleNamespace(
            blocks=[SimpleNamespace(text="正文")],
            parser_name="fake-parser",
        ),
    )
    monkeypatch.setattr(ingestion_tasks, "build_chunks", lambda *_args, **_kwargs: [{"content": "chunk body"}])
    monkeypatch.setattr(ingestion_tasks, "_generate_preview_metadata", AsyncMock(return_value={}))
    monkeypatch.setattr(ingestion_tasks, "_generate_docling_artifact_metadata", AsyncMock(return_value={}))
    monkeypatch.setattr(ingestion_tasks, "_build_truth_signature_metadata", lambda **_kwargs: {})
    monkeypatch.setattr(ingestion_tasks, "generate_embeddings_batch", _fake_generate_embeddings)
    monkeypatch.setattr(ingestion_tasks, "_persist_ingestion_job_status", _fake_persist_status)
    monkeypatch.setattr(ingestion_tasks.process_document, "retry", _unexpected_retry)

    with pytest.raises(EmbeddingProviderError, match="Arrearage"):
        ingestion_tasks.process_document.run(str(job_id))

    assert retry_calls == []
    assert persisted_states == [
        {
            "job_id": job_id,
            "status": JobStatus.FAILED,
            "progress": 70,
            "error_message": "DashScope embedding request failed (status=400, code=Arrearage): account overdue",
        }
    ]
    cleanup_mock.assert_awaited_once_with("tmp-file.pdf")


def test_process_document_skips_detached_deleted_job(monkeypatch):
    job_id = uuid4()
    download_mock = AsyncMock()

    job = SimpleNamespace(
        id=job_id,
        status=JobStatus.FAILED,
        object_path="documents/deleted.pdf",
        file_type="pdf",
        knowledge_point_id=None,
    )

    class _FakeJobRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, incoming_job_id: UUID):
            assert incoming_job_id == job_id
            return job

        async def update_status(self, incoming_job_id: UUID, **kwargs):
            raise AssertionError("update_status should not be called for detached deleted jobs")

    class _FakeKnowledgePointRepo:
        def __init__(self, session):
            self.session = session

    monkeypatch.setattr(ingestion_tasks, "init_db_engine", lambda: None)
    monkeypatch.setattr(ingestion_tasks, "_run_async", _run_immediately)
    monkeypatch.setattr(ingestion_tasks, "get_celery_session", lambda: _AsyncSessionContext(object()))
    monkeypatch.setattr(ingestion_tasks, "IngestionJobRepository", _FakeJobRepo)
    monkeypatch.setattr(ingestion_tasks, "KnowledgePointRepository", _FakeKnowledgePointRepo)
    monkeypatch.setattr(ingestion_tasks, "download_from_minio_async", download_mock)

    result = ingestion_tasks.process_document.run(str(job_id))

    assert result == {
        "status": "failed",
        "chunks": 0,
        "skipped": True,
        "reason": "knowledge_point_deleted",
    }
    download_mock.assert_not_awaited()
