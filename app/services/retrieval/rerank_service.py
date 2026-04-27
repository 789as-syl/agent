"""Rerank retrieval candidates by semantic relevance."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Any

from dashscope import TextReRank

from app.core.config import settings
from app.core.log_config import get_logger

logger = get_logger(__name__)


class RerankService:
    """Rerank retrieval candidates by semantic relevance."""

    def __init__(self) -> None:
        self.model = settings.retrieval_rerank_model
        self.api_key = settings.dashscope_api_key
        self.default_top_n = settings.retrieval_rerank_top_n

    @staticmethod
    def _build_document_text(document: dict[str, Any]) -> str:
        title = str(document.get("title") or document.get("knowledge_point_title") or "").strip()
        content = str(
            document.get("content")
            or document.get("knowledge_point_content")
            or document.get("chunk_content")
            or ""
        ).strip()
        return "\n".join(part for part in (title, content) if part)

    async def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        if not documents:
            return []

        try:
            resolved_top_n = max(1, min(int(top_n or self.default_top_n), len(documents)))
            response = await asyncio.to_thread(
                TextReRank.call,
                model=self.model,
                query=str(query or "").strip(),
                documents=[self._build_document_text(document) for document in documents],
                top_n=resolved_top_n,
                api_key=self.api_key,
            )

            if getattr(response, "status_code", None) != int(HTTPStatus.OK):
                raise RuntimeError(
                    "DashScope rerank request failed "
                    f"(status={getattr(response, 'status_code', None)}, "
                    f"code={getattr(response, 'code', None)}, "
                    f"request_id={getattr(response, 'request_id', None)}): "
                    f"{getattr(response, 'message', 'unknown provider error')}"
                )

            results = getattr(getattr(response, "output", None), "results", None)
            if not isinstance(results, list):
                raise RuntimeError("DashScope rerank response did not include results")

            reranked_docs: list[dict[str, Any]] = []
            for result in results:
                original_idx = int(getattr(result, "index", -1))
                if 0 <= original_idx < len(documents):
                    doc = documents[original_idx].copy()
                    doc["rerank_score"] = float(getattr(result, "relevance_score", 0.0) or 0.0)
                    reranked_docs.append(doc)

            logger.info("rerank complete: %s -> %s", len(documents), len(reranked_docs))
            return reranked_docs
        except Exception as exc:
            logger.error("rerank failed: %s", exc, exc_info=True)
            return documents[:top_n]
