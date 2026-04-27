"""Tests for retrieval-path performance guards and optimizations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.embedding_utils import EmbeddingProviderError
from app.schemas.retrieval import RetrievalConfig
from app.services.retrieval.embedding_service import EmbeddingService
from app.services.retrieval.rerank_service import RerankService
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.vector_search_service import VectorSearchService


class _DummySession:
    @asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[None]:
        yield

    async def rollback(self) -> None:
        return None


def _dummy_session_factory():
    @asynccontextmanager
    async def _session_ctx() -> AsyncIterator[_DummySession]:
        yield _DummySession()

    return _session_ctx()


@pytest.mark.asyncio
async def test_vector_search_service_isolated_sessions_disable_inline_count_updates() -> None:
    primary_session = _DummySession()
    kp_repo = MagicMock()
    kp_repo.session = primary_session
    question_repo = MagicMock()
    question_repo.session = primary_session

    with (
        patch(
            "app.services.retrieval.vector_search_service.KnowledgePointRepository.vector_search",
            new_callable=AsyncMock,
        ) as mock_kp_search,
        patch(
            "app.services.retrieval.vector_search_service.QuestionRepository.vector_search",
            new_callable=AsyncMock,
        ) as mock_question_search,
    ):
        mock_kp_search.return_value = [
            {
                "chunk_id": uuid4(),
                "knowledge_point_id": uuid4(),
                "similarity": 0.91,
            }
        ]
        mock_question_search.return_value = [
            {
                "question_id": uuid4(),
                "similarity": 0.83,
            }
        ]

        service = VectorSearchService(
            kp_repo=kp_repo,
            question_repo=question_repo,
            session_factory=_dummy_session_factory,
        )

        kp_results, question_results = await service.parallel_search(
            embedding=[0.1, 0.2, 0.3],
            top_k=5,
            similarity_threshold=0.7,
        )

        assert service.defer_retrieval_count_updates is True
        assert len(kp_results) == 1
        assert len(question_results) == 1
        assert mock_kp_search.await_count == 1
        assert mock_kp_search.await_args.kwargs["update_retrieval_count"] is False


@pytest.mark.asyncio
async def test_update_retrieval_counts_keeps_group_calls() -> None:
    service = RetrievalService.__new__(RetrievalService)
    service.kp_repo = MagicMock()
    service.kp_repo.increment_retrieval_counts = AsyncMock()

    chunk_a = uuid4()
    chunk_b = uuid4()

    await service._update_retrieval_counts(
        [{"chunk_id": chunk_a}, {"chunk_id": chunk_a}],
        [{"chunk_id": str(chunk_b)}],
    )

    assert service.kp_repo.increment_retrieval_counts.await_count == 2

    first_call_ids = service.kp_repo.increment_retrieval_counts.await_args_list[0].args[0]
    second_call_ids = service.kp_repo.increment_retrieval_counts.await_args_list[1].args[0]

    assert first_call_ids == [chunk_a, chunk_a]
    assert second_call_ids == [chunk_b]


@pytest.mark.asyncio
async def test_embedding_generate_batch_deduplicates_normalized_inputs() -> None:
    service = EmbeddingService.__new__(EmbeddingService)
    service.generate = AsyncMock(side_effect=[[0.1, 0.2], [0.3, 0.4]])

    results = await EmbeddingService.generate_batch(service, ["same query", " same query ", "other query"])

    assert results == [[0.1, 0.2], [0.1, 0.2], [0.3, 0.4]]
    assert service.generate.await_count == 2
    assert [call.args[0] for call in service.generate.await_args_list] == ["same query", "other query"]


@pytest.mark.asyncio
async def test_embedding_generate_uses_normalized_dashscope_helper_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    service = EmbeddingService.__new__(EmbeddingService)
    service.model = "text-embedding-v3"
    service.dimension = 2
    service.batch_size = 8
    service.api_key = "test-key"
    service.get_from_cache = AsyncMock(return_value=None)
    service.save_to_cache = AsyncMock(return_value=None)

    helper_calls: list[dict[str, object]] = []

    async def _fake_generate_dashscope_embeddings(texts: list[str], **kwargs: object) -> list[list[float]]:
        helper_calls.append({"texts": texts, **kwargs})
        return [[0.11, 0.22]]

    monkeypatch.setattr(
        "app.services.retrieval.embedding_service.generate_dashscope_embeddings",
        _fake_generate_dashscope_embeddings,
    )

    result = await EmbeddingService.generate(service, "  query text  ")

    assert result == [0.11, 0.22]
    assert helper_calls == [
        {
            "texts": ["query text"],
            "model_name": "text-embedding-v3",
            "api_key": "test-key",
            "batch_size": 8,
            "text_type": "query",
            "expected_dimension": 2,
        }
    ]
    service.save_to_cache.assert_awaited_once_with("query text", [0.11, 0.22])


@pytest.mark.asyncio
async def test_embedding_generate_surfaces_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = EmbeddingService.__new__(EmbeddingService)
    service.model = "text-embedding-v3"
    service.dimension = 1024
    service.batch_size = 8
    service.api_key = "test-key"
    service.get_from_cache = AsyncMock(return_value=None)
    service.save_to_cache = AsyncMock(return_value=None)

    async def _fake_generate_dashscope_embeddings(texts: list[str], **kwargs: object) -> list[list[float]]:
        raise EmbeddingProviderError(
            "DashScope embedding request failed (status=400, code=Arrearage): account overdue",
            retryable=False,
            status_code=400,
            code="Arrearage",
        )

    monkeypatch.setattr(
        "app.services.retrieval.embedding_service.generate_dashscope_embeddings",
        _fake_generate_dashscope_embeddings,
    )

    with pytest.raises(EmbeddingProviderError, match="Arrearage"):
        await EmbeddingService.generate(service, "query text")

    service.save_to_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_rerank_service_calls_dashscope_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RerankService.__new__(RerankService)
    service.model = "gte-rerank"
    service.api_key = "test-key"
    service.default_top_n = 3

    documents = [
        {"knowledge_point_id": "kp-1", "knowledge_point_title": "标题 1", "chunk_content": "内容 1"},
        {"knowledge_point_id": "kp-2", "knowledge_point_content": "内容 2"},
    ]
    provider_calls: list[dict[str, object]] = []

    def _fake_rerank_call(**kwargs: object) -> SimpleNamespace:
        provider_calls.append(kwargs)
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                results=[
                    SimpleNamespace(index=1, relevance_score=0.91),
                    SimpleNamespace(index=0, relevance_score=0.73),
                ]
            ),
        )

    monkeypatch.setattr("app.services.retrieval.rerank_service.TextReRank.call", _fake_rerank_call)

    result = await RerankService.rerank(service, "查询词", documents, top_n=5)

    assert provider_calls == [
        {
            "model": "gte-rerank",
            "query": "查询词",
            "documents": ["标题 1\n内容 1", "内容 2"],
            "top_n": 2,
            "api_key": "test-key",
        }
    ]
    assert result == [
        {"knowledge_point_id": "kp-2", "knowledge_point_content": "内容 2", "rerank_score": 0.91},
        {
            "knowledge_point_id": "kp-1",
            "knowledge_point_title": "标题 1",
            "chunk_content": "内容 1",
            "rerank_score": 0.73,
        },
    ]


@pytest.mark.asyncio
async def test_rerank_service_falls_back_when_provider_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RerankService.__new__(RerankService)
    service.model = "gte-rerank"
    service.api_key = "test-key"
    service.default_top_n = 3

    documents = [
        {"knowledge_point_id": "kp-1", "knowledge_point_title": "标题 1", "chunk_content": "内容 1"},
        {"knowledge_point_id": "kp-2", "knowledge_point_content": "内容 2"},
    ]

    def _fake_rerank_call(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=400,
            code="Arrearage",
            request_id="req-1",
            message="account overdue",
            output=None,
        )

    monkeypatch.setattr("app.services.retrieval.rerank_service.TextReRank.call", _fake_rerank_call)

    result = await RerankService.rerank(service, "查询词", documents, top_n=1)

    assert result == [documents[0]]


def test_select_best_candidates_prefers_highest_similarity_and_order() -> None:
    kp_1 = uuid4()
    kp_2 = uuid4()

    results = [
        {"knowledge_point_id": kp_1, "similarity": 0.72, "chunk_content": "older"},
        {"knowledge_point_id": kp_2, "similarity": 0.81, "chunk_content": "best-kp2"},
        {"knowledge_point_id": kp_1, "similarity": 0.93, "chunk_content": "best-kp1"},
    ]

    selected = RetrievalService._select_best_candidates(
        all_kp_results=results,
        top_kp_ids=[str(kp_2), str(kp_1)],
    )

    assert [str(item["knowledge_point_id"]) for item in selected] == [str(kp_2), str(kp_1)]
    assert selected[0]["chunk_content"] == "best-kp2"
    assert selected[1]["chunk_content"] == "best-kp1"


def test_build_evidence_content_accepts_list_provenance_entries() -> None:
    service = RetrievalService.__new__(RetrievalService)
    chunks = [
        SimpleNamespace(
            chunk_index=0,
            content="第一块",
            metadata_json={"provenance": [{"page_number": 1}, {"page_number": 2}]},
        ),
        SimpleNamespace(
            chunk_index=1,
            content="第二块",
            metadata_json={"provenance": [{"page_number": 3}]},
        ),
    ]

    content, provenance = RetrievalService._build_evidence_content(
        service,
        chunks,
        {"anchor_group_type": "section"},
        table_neighbor_rows=1,
    )

    assert content == "第一块\n第二块"
    assert provenance == [{"page_number": 1}, {"page_number": 2}, {"page_number": 3}]


@pytest.mark.asyncio
async def test_retrieve_short_circuits_when_no_vectorized_data() -> None:
    service = RetrievalService.__new__(RetrievalService)
    service.config = RetrievalConfig(enable_cache=False)
    service.db_session = MagicMock()
    service.kp_repo = MagicMock()
    service.kp_repo.count_vectorized_chunks = AsyncMock(return_value=0)
    service.question_repo = MagicMock()
    service.question_repo.count_vectorized_questions = AsyncMock(return_value=0)
    service._get_from_cache = AsyncMock(return_value=None)

    response = await service.retrieve(
        query="???????????????",
        user_id=uuid4(),
        conversation_id=uuid4(),
        config=service.config,
    )

    assert response.knowledge_points == []
    assert response.explanation.cache_hit is False
    assert response.explanation.direct_hit_count == 0
    service.kp_repo.count_vectorized_chunks.assert_awaited_once()
    service.question_repo.count_vectorized_questions.assert_awaited_once()
