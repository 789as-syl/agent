"""Embedding generation and Redis caching helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence

from app.core.config import settings
from app.core.embedding_utils import generate_dashscope_embeddings
from app.core.log_config import get_logger
from app.core.redis import redis_client

logger = get_logger(__name__)


class EmbeddingService:
    """Generate embeddings using DashScope and cache them in Redis."""

    def __init__(self, cache_ttl: int = 86400) -> None:
        self.cache_ttl = cache_ttl
        self.model = settings.retrieval_embedding_model
        self.dimension = settings.retrieval_embedding_dimension
        self.batch_size = settings.retrieval_embedding_batch_size
        self.api_key = settings.dashscope_api_key

    def _get_cache_key(self, text: str, *, text_type: str = "query") -> str:
        text_hash = hashlib.sha256(f"{text_type}:{text}".encode()).hexdigest()
        return f"embedding:{text_hash}"

    async def get_from_cache(self, text: str, *, text_type: str = "query") -> list[float] | None:
        cache_key = self._get_cache_key(text, text_type=text_type)
        cached = await redis_client.get(cache_key)
        if not cached:
            return None

        try:
            embedding = json.loads(cached)
        except Exception:
            logger.warning("embedding cache decode failed, ignore cache")
            return None

        if self._is_valid_embedding(embedding):
            logger.debug("embedding cache hit: %s...", text[:50])
            return [float(x) for x in embedding]

        logger.warning("embedding cache value invalid, ignore cache")
        return None

    async def save_to_cache(self, text: str, embedding: list[float], *, text_type: str = "query") -> None:
        cache_key = self._get_cache_key(text, text_type=text_type)
        await redis_client.setex(cache_key, self.cache_ttl, json.dumps(embedding))

    def _is_valid_embedding(self, embedding: object) -> bool:
        if not isinstance(embedding, Sequence):
            return False
        if len(embedding) != self.dimension:
            return False
        return all(isinstance(x, (float, int)) for x in embedding)

    async def generate(self, text: str) -> list[float]:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text cannot be embedded")

        cached = await self.get_from_cache(text)
        if cached is not None:
            return cached

        try:
            embedding = (
                await generate_dashscope_embeddings(
                    [text],
                    model_name=self.model,
                    api_key=self.api_key,
                    batch_size=self.batch_size,
                    text_type="query",
                    expected_dimension=self.dimension,
                )
            )[0]
        except Exception as exc:
            logger.error("embedding generation failed: %s", exc, exc_info=True)
            raise

        await self.save_to_cache(text, embedding)
        logger.debug("embedding generated: %s...", text[:50])
        return embedding

    async def generate_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        normalized_positions: dict[str, list[int]] = {}
        for index, text in enumerate(texts):
            normalized = (text or "").strip()
            if not normalized:
                raise ValueError("empty text cannot be embedded")
            normalized_positions.setdefault(normalized, []).append(index)

        unique_texts = list(normalized_positions)
        unique_embeddings = await asyncio.gather(*(self.generate(text) for text in unique_texts))

        ordered_results: list[list[float] | None] = [None] * len(texts)
        for text, embedding in zip(unique_texts, unique_embeddings, strict=True):
            for index in normalized_positions[text]:
                ordered_results[index] = embedding.copy()

        resolved_results: list[list[float]] = []
        for resolved_item in ordered_results:
            if resolved_item is None:  # pragma: no cover - defensive invariant
                raise RuntimeError("embedding batch result missing")
            resolved_results.append(list(resolved_item))
        return resolved_results
