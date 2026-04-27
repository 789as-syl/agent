"""Unit tests for vectorization tasks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.core.embedding_utils import EmbeddingProviderError
from app.models.enums import JobStatus
from app.repositories.question_repo import compute_embedding_text_hash
from app.tasks import vectorization_tasks


class _AsyncSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _run_immediately(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def test_finalize_batch_marks_job_failed_on_partial_failures(monkeypatch):
    updated: list[dict] = []

    class _FakeJobRepo:
        def __init__(self, session):
            self.session = session

        async def update_status(self, job_id, **kwargs):
            updated.append({"job_id": job_id, **kwargs})
            return None

    delete_mock = AsyncMock(return_value=1)

    monkeypatch.setattr(vectorization_tasks, "init_db_engine", lambda: None)
    monkeypatch.setattr(vectorization_tasks, "_run_async", _run_immediately)
    monkeypatch.setattr(vectorization_tasks, "get_celery_session", _AsyncSessionContext)
    monkeypatch.setattr(vectorization_tasks, "VectorizationJobRepository", _FakeJobRepo)
    monkeypatch.setattr(vectorization_tasks.redis_client, "delete", delete_mock)

    job_id = str(uuid4())
    result = vectorization_tasks.finalize_batch.run(
        [{"status": "success"}, {"status": "failed"}, {"status": "skipped"}],
        job_id,
    )

    assert result == {"status": "completed", "success": 1, "skipped": 1, "failed": 1}
    assert updated[-1]["status"] == JobStatus.FAILED
    assert updated[-1]["processed_questions"] == 3
    assert updated[-1]["error_message"] == "1 questions failed to vectorize"
    delete_mock.assert_any_await(f"{vectorization_tasks.VECTORIZATION_LOCK_KEY}:{job_id}")
    delete_mock.assert_any_await(vectorization_tasks.VECTORIZATION_LOCK_KEY)


def test_vectorize_question_refreshes_stale_hash_even_when_embedding_exists(monkeypatch):
    stored_payloads: list[dict] = []
    increment_mock = AsyncMock(return_value=None)
    question_id = uuid4()
    job_id = uuid4()

    question = SimpleNamespace(
        id=question_id,
        question_text="需要回填 hash 的题目",
        question_embedding=[0.1, 0.2],
        embedding_text_hash=None,
        is_dirty=False,
    )

    class _FakeQuestionRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, incoming_question_id: UUID):
            assert incoming_question_id == question_id
            return question

        async def bulk_store_embeddings(self, payloads: list[dict]):
            stored_payloads.extend(payloads)
            return len(payloads)

    class _FakeJobRepo:
        def __init__(self, session):
            self.session = session

        async def increment_processed_count(self, incoming_job_id: UUID):
            await increment_mock(incoming_job_id)

    monkeypatch.setattr(vectorization_tasks, "init_db_engine", lambda: None)
    monkeypatch.setattr(vectorization_tasks, "_run_async", _run_immediately)
    monkeypatch.setattr(vectorization_tasks, "get_celery_session", _AsyncSessionContext)
    monkeypatch.setattr(vectorization_tasks, "QuestionRepository", _FakeQuestionRepo)
    monkeypatch.setattr(vectorization_tasks, "VectorizationJobRepository", _FakeJobRepo)
    async def _fake_generate_embeddings(texts: list[str], **_: object) -> list[list[float]]:
        return [[0.3, 0.4] for _ in texts]

    monkeypatch.setattr(vectorization_tasks, "generate_dashscope_embeddings", _fake_generate_embeddings)

    response = vectorization_tasks.vectorize_question.run(str(question_id), str(job_id))

    assert response["status"] == "success"
    assert stored_payloads[0]["question_id"] == question_id
    assert stored_payloads[0]["embedding"] == "[0.3,0.4]"
    assert stored_payloads[0]["embedding_text_hash"] == compute_embedding_text_hash(question.question_text)
    increment_mock.assert_awaited_once_with(job_id)


def test_batch_vectorize_pages_candidates_and_skips_up_to_date_questions(monkeypatch):
    job_id = uuid4()
    question_id_1 = uuid4()
    question_id_2 = uuid4()
    question_id_3 = uuid4()
    delete_mock = AsyncMock(return_value=1)

    job = SimpleNamespace(
        id=job_id,
        status=JobStatus.PENDING,
        progress=0,
        total_questions=0,
        processed_questions=0,
        error_message="old-error",
    )
    updates: list[dict] = []
    stored_payloads: list[dict] = []

    questions = {
        question_id_1: SimpleNamespace(
            id=question_id_1,
            question_text="题目 1",
            question_embedding=None,
            embedding_text_hash=None,
            is_dirty=True,
        ),
        question_id_2: SimpleNamespace(
            id=question_id_2,
            question_text="题目 2",
            question_embedding=[0.5, 0.6],
            embedding_text_hash=compute_embedding_text_hash("题目 2"),
            is_dirty=False,
        ),
        question_id_3: SimpleNamespace(
            id=question_id_3,
            question_text="题目 3",
            question_embedding=None,
            embedding_text_hash=None,
            is_dirty=True,
        ),
    }

    class _FakeQuestionRepo:
        def __init__(self, session):
            self.session = session

        async def count_vectorization_candidates(self, only_dirty: bool = True):
            assert only_dirty is True
            return 3

        async def list_vectorization_candidate_page(
            self,
            *,
            only_dirty: bool = True,
            limit: int = 100,
            last_created_at=None,
            last_id=None,
        ):
            assert only_dirty is True
            assert limit == 2
            if last_created_at is None and last_id is None:
                return [(question_id_1, 1), (question_id_2, 2)]
            if last_id == question_id_2:
                return [(question_id_3, 3)]
            return []

        async def get_by_ids(self, question_ids: list[UUID]):
            return [questions[question_id] for question_id in question_ids if question_id in questions]

        async def bulk_store_embeddings(self, payloads: list[dict]):
            stored_payloads.extend(payloads)
            return len(payloads)

    class _FakeJobRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, incoming_job_id: UUID):
            assert incoming_job_id == job_id
            return job

        async def update_status(self, incoming_job_id: UUID, **kwargs):
            assert incoming_job_id == job_id
            updates.append(kwargs)
            if "status" in kwargs and kwargs["status"] is not None:
                job.status = kwargs["status"]
            if "progress" in kwargs and kwargs["progress"] is not None:
                job.progress = kwargs["progress"]
            if "total_questions" in kwargs and kwargs["total_questions"] is not None:
                job.total_questions = kwargs["total_questions"]
            if "processed_questions" in kwargs and kwargs["processed_questions"] is not None:
                job.processed_questions = kwargs["processed_questions"]
            if "error_message" in kwargs:
                job.error_message = kwargs["error_message"]
            return job

    def _fake_embed_batch(texts: list[str]) -> list[list[float]]:
        mapping = {
            "题目 1": [0.11, 0.12],
            "题目 3": [0.31, 0.32],
        }
        return [mapping[text] for text in texts]

    monkeypatch.setattr(vectorization_tasks, "init_db_engine", lambda: None)
    monkeypatch.setattr(vectorization_tasks, "_run_async", _run_immediately)
    monkeypatch.setattr(vectorization_tasks, "get_celery_session", _AsyncSessionContext)
    monkeypatch.setattr(vectorization_tasks, "QuestionRepository", _FakeQuestionRepo)
    monkeypatch.setattr(vectorization_tasks, "VectorizationJobRepository", _FakeJobRepo)
    async def _fake_generate_embeddings(texts: list[str], **_: object) -> list[list[float]]:
        return _fake_embed_batch(texts)

    monkeypatch.setattr(vectorization_tasks, "generate_dashscope_embeddings", _fake_generate_embeddings)
    monkeypatch.setattr(vectorization_tasks.redis_client, "set", AsyncMock(return_value=True))
    monkeypatch.setattr(vectorization_tasks.redis_client, "delete", delete_mock)

    result = vectorization_tasks.batch_vectorize.run(str(job_id), True, 2)

    assert result == {
        "status": "success",
        "job_id": str(job_id),
        "total": 3,
        "processed": 3,
    }
    assert job.status == JobStatus.SUCCESS
    assert job.total_questions == 3
    assert job.processed_questions == 3
    assert job.progress == 100
    assert job.error_message is None
    assert [payload["question_id"] for payload in stored_payloads] == [question_id_1, question_id_3]
    assert stored_payloads[0]["embedding"] == "[0.11,0.12]"
    assert stored_payloads[1]["embedding_text_hash"] == compute_embedding_text_hash("题目 3")
    assert any(update.get("processed_questions") == 2 for update in updates)
    delete_mock.assert_any_await(f"{vectorization_tasks.VECTORIZATION_LOCK_KEY}:{job_id}")
    delete_mock.assert_any_await(vectorization_tasks.VECTORIZATION_LOCK_KEY)


def test_generate_embeddings_batch_surfaces_provider_error(monkeypatch):
    async def _fake_generate_embeddings(*args, **kwargs):
        raise EmbeddingProviderError(
            "DashScope embedding request failed (status=400, code=Arrearage): account overdue",
            retryable=False,
            status_code=400,
            code="Arrearage",
        )

    monkeypatch.setattr(vectorization_tasks, "generate_dashscope_embeddings", _fake_generate_embeddings)

    with pytest.raises(EmbeddingProviderError, match="Arrearage"):
        _run_immediately(vectorization_tasks._generate_embeddings_batch(["题目 A"]))


def test_batch_vectorize_marks_failed_without_retry_for_permanent_embedding_error(monkeypatch):
    job_id = uuid4()
    delete_mock = AsyncMock(return_value=1)
    retry_calls: list[dict] = []

    job = SimpleNamespace(
        id=job_id,
        status=JobStatus.PENDING,
        progress=0,
        total_questions=0,
        processed_questions=0,
        error_message=None,
    )
    updates: list[dict] = []

    question = SimpleNamespace(
        id=uuid4(),
        question_text="失败题目",
        question_embedding=None,
        embedding_text_hash=None,
        is_dirty=True,
    )

    class _FakeQuestionRepo:
        def __init__(self, session):
            self.session = session

        async def count_vectorization_candidates(self, only_dirty: bool = True):
            assert only_dirty is True
            return 1

        async def list_vectorization_candidate_page(self, **kwargs):
            if kwargs.get("last_id") is None:
                return [(question.id, 1)]
            return []

        async def get_by_ids(self, question_ids: list[UUID]):
            assert question_ids == [question.id]
            return [question]

        async def bulk_store_embeddings(self, payloads: list[dict]):
            raise AssertionError("bulk_store_embeddings should not be called on permanent embedding failure")

    class _FakeJobRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_id(self, incoming_job_id: UUID):
            assert incoming_job_id == job_id
            return job

        async def update_status(self, incoming_job_id: UUID, **kwargs):
            assert incoming_job_id == job_id
            updates.append(kwargs)
            if "status" in kwargs and kwargs["status"] is not None:
                job.status = kwargs["status"]
            if "progress" in kwargs and kwargs["progress"] is not None:
                job.progress = kwargs["progress"]
            if "total_questions" in kwargs and kwargs["total_questions"] is not None:
                job.total_questions = kwargs["total_questions"]
            if "processed_questions" in kwargs and kwargs["processed_questions"] is not None:
                job.processed_questions = kwargs["processed_questions"]
            if "error_message" in kwargs:
                job.error_message = kwargs["error_message"]
            return job

    async def _fake_generate_embeddings(*args, **kwargs):
        raise EmbeddingProviderError(
            "DashScope embedding request failed (status=400, code=Arrearage): account overdue",
            retryable=False,
            status_code=400,
            code="Arrearage",
        )

    def _unexpected_retry(*args, **kwargs):
        retry_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("retry should not be called for permanent embedding failures")

    monkeypatch.setattr(vectorization_tasks, "init_db_engine", lambda: None)
    monkeypatch.setattr(vectorization_tasks, "_run_async", _run_immediately)
    monkeypatch.setattr(vectorization_tasks, "get_celery_session", _AsyncSessionContext)
    monkeypatch.setattr(vectorization_tasks, "QuestionRepository", _FakeQuestionRepo)
    monkeypatch.setattr(vectorization_tasks, "VectorizationJobRepository", _FakeJobRepo)
    monkeypatch.setattr(vectorization_tasks, "generate_dashscope_embeddings", _fake_generate_embeddings)
    monkeypatch.setattr(vectorization_tasks.redis_client, "set", AsyncMock(return_value=True))
    monkeypatch.setattr(vectorization_tasks.redis_client, "delete", delete_mock)
    monkeypatch.setattr(vectorization_tasks.batch_vectorize, "retry", _unexpected_retry)

    with pytest.raises(EmbeddingProviderError, match="Arrearage"):
        vectorization_tasks.batch_vectorize.run(str(job_id), True, 1)

    assert retry_calls == []
    assert job.status == JobStatus.FAILED
    assert "Arrearage" in str(job.error_message)
    delete_mock.assert_any_await(f"{vectorization_tasks.VECTORIZATION_LOCK_KEY}:{job_id}")
