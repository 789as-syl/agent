"""Vector and lexical search helpers for knowledge-point chunks."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.log_config import get_logger
from app.repositories.knowledge_point_repo import KnowledgePointRepository
from app.repositories.question_repo import QuestionRepository

logger = get_logger(__name__)


class VectorSearchService:
    """Execute dense and lexical search against knowledge-point chunks."""

    def __init__(
        self,
        kp_repo: KnowledgePointRepository,
        question_repo: QuestionRepository | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self.kp_repo = kp_repo
        self.question_repo = question_repo
        self.session_factory = session_factory

    async def search_knowledge_points(
        self,
        embedding: list[float],
        *,
        top_k: int = 10,
        similarity_threshold: float = 0.7,
        update_retrieval_count: bool = True,
    ) -> list[dict[str, Any]]:
        return await self.kp_repo.vector_search(
            embedding=embedding,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            update_retrieval_count=update_retrieval_count,
        )

    async def search_keyword(
        self,
        query: str,
        *,
        top_k: int = 10,
        update_retrieval_count: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            return await self.kp_repo.keyword_search(
                query=query,
                top_k=top_k,
                update_retrieval_count=update_retrieval_count,
            )
        except Exception as exc:
            logger.warning("keyword search unavailable", error=str(exc))
            return []

    async def search_questions(
        self,
        embedding: list[float],
        top_k: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        if self.question_repo is None:
            return []
        try:
            return await self.question_repo.vector_search(
                embedding=embedding,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
            )
        except Exception as exc:
            logger.warning("question vector search unavailable", error=str(exc))
            return []

    @property
    def defer_retrieval_count_updates(self) -> bool:
        return self.session_factory is not None

    async def parallel_search(
        self,
        embedding: list[float],
        top_k: int = 10,
        similarity_threshold: float = 0.7,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if self.session_factory is not None:
            async with self.session_factory() as kp_session, self.session_factory() as question_session:
                isolated_service = VectorSearchService(
                    kp_repo=KnowledgePointRepository(kp_session),
                    question_repo=QuestionRepository(question_session),
                )
                return await asyncio.gather(
                    isolated_service.search_knowledge_points(
                        embedding=embedding,
                        top_k=top_k,
                        similarity_threshold=similarity_threshold,
                        update_retrieval_count=False,
                    ),
                    isolated_service.search_questions(
                        embedding=embedding,
                        top_k=top_k,
                        similarity_threshold=similarity_threshold,
                    ),
                )
        dense_task = self.search_knowledge_points(
            embedding=embedding,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            update_retrieval_count=True,
        )
        question_task = self.search_questions(
            embedding=embedding,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )
        return await asyncio.gather(dense_task, question_task)
