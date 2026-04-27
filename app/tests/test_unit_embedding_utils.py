"""Unit tests for shared embedding helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any

import pytest

from app.core import embedding_utils


def _run_immediately(coro: Coroutine[Any, Any, Any]) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def test_generate_dashscope_embeddings_respects_dashscope_batch_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_inputs: list[list[str]] = []

    def _fake_text_embedding_call(**kwargs: Any) -> SimpleNamespace:
        batch = list(kwargs["input"])
        recorded_inputs.append(batch)
        return SimpleNamespace(
            status_code=200,
            output={
                "embeddings": [
                    {"text_index": index, "embedding": [float(index)]}
                    for index, _ in enumerate(batch)
                ]
            },
        )

    monkeypatch.setattr(embedding_utils.TextEmbedding, "call", _fake_text_embedding_call)
    monkeypatch.setattr(embedding_utils.settings, "dashscope_embedding_max_batch_size", 10)

    texts = [f"chunk-{index}" for index in range(11)]
    result = _run_immediately(
        embedding_utils.generate_dashscope_embeddings(
            texts,
            model_name="text-embedding-v3",
            api_key="test-key",
            batch_size=25,
        )
    )

    assert len(result) == 11
    assert recorded_inputs == [texts[:10], texts[10:]]


def test_generate_dashscope_embeddings_retries_with_smaller_batches_on_provider_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_batch_sizes: list[int] = []

    def _fake_text_embedding_call(**kwargs: Any) -> SimpleNamespace:
        batch = list(kwargs["input"])
        recorded_batch_sizes.append(len(batch))
        if len(batch) > 10:
            return SimpleNamespace(
                status_code=400,
                code="InvalidParameter",
                request_id="req-batch-limit",
                message=(
                    "<400> InternalError.Algo.InvalidParameter: Value error, "
                    "batch size is invalid, it should not be larger than 10.: input.contents"
                ),
            )
        return SimpleNamespace(
            status_code=200,
            output={
                "embeddings": [
                    {"text_index": index, "embedding": [float(index), float(len(batch))]}
                    for index, _ in enumerate(batch)
                ]
            },
        )

    monkeypatch.setattr(embedding_utils.TextEmbedding, "call", _fake_text_embedding_call)
    monkeypatch.setattr(embedding_utils.settings, "dashscope_embedding_max_batch_size", 20)

    texts = [f"chunk-{index}" for index in range(14)]
    result = _run_immediately(
        embedding_utils.generate_dashscope_embeddings(
            texts,
            model_name="text-embedding-v3",
            api_key="test-key",
            batch_size=25,
        )
    )

    assert len(result) == 14
    assert recorded_batch_sizes == [14, 7, 7]
