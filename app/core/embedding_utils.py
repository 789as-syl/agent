"""Shared DashScope embedding helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from http import HTTPStatus

from dashscope import TextEmbedding

from app.core.config import settings


class EmbeddingProviderError(RuntimeError):
    """Embedding provider failure with retryability metadata."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        provider: str = "DashScope",
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.retryable = retryable
        self.provider = provider
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        super().__init__(message)


_NON_RETRYABLE_CODE_MARKERS = {
    "arrearage",
    "invalidapikey",
    "invalid_api_key",
    "unauthorized",
    "forbidden",
    "permissiondenied",
    "modelnotfound",
}

_NON_RETRYABLE_MESSAGE_MARKERS = (
    "arrearage",
    "overdue",
    "good standing",
    "access denied",
    "unauthorized",
    "invalid api key",
    "api key is invalid",
    "permission denied",
    "forbidden",
    "model not found",
    "bad request",
    "invalid parameter",
    "illegal parameter",
)

_RETRYABLE_MESSAGE_MARKERS = (
    "timeout",
    "timed out",
    "temporarily unavailable",
    "temporary",
    "try again",
    "rate limit",
    "too many requests",
    "throttle",
    "connection reset",
    "connection aborted",
    "connection refused",
    "gateway timeout",
    "bad gateway",
    "service unavailable",
    "internal error",
)

_BATCH_LIMIT_MESSAGE_MARKERS = (
    "batch size is invalid",
    "should not be larger than",
    "input.contents",
)


def _normalize_error_text(*parts: object) -> str:
    return " ".join(str(part).strip().lower() for part in parts if part is not None).strip()


def _is_provider_batch_limit_error(
    *,
    status_code: int | None = None,
    code: str | None = None,
    message: str | None = None,
) -> bool:
    normalized_text = _normalize_error_text(code, message)
    if status_code is not None and int(status_code) != int(HTTPStatus.BAD_REQUEST):
        return False
    if "invalidparameter" not in normalized_text and "invalid parameter" not in normalized_text:
        return False
    return any(marker in normalized_text for marker in _BATCH_LIMIT_MESSAGE_MARKERS)


def is_retryable_task_exception(exc: Exception) -> bool:
    """Return whether the current task exception should be retried."""
    if isinstance(exc, EmbeddingProviderError):
        return exc.retryable
    return not isinstance(exc, ValueError)


def _is_retryable_provider_failure(
    *,
    status_code: int | None = None,
    code: str | None = None,
    message: str | None = None,
) -> bool:
    normalized_code = (code or "").strip().lower().replace("_", "")
    normalized_text = _normalize_error_text(code, message)

    if normalized_code in _NON_RETRYABLE_CODE_MARKERS:
        return False
    if any(marker in normalized_text for marker in _NON_RETRYABLE_MESSAGE_MARKERS):
        return False

    if status_code is not None:
        if status_code in {
            int(HTTPStatus.REQUEST_TIMEOUT),
            int(HTTPStatus.TOO_MANY_REQUESTS),
            int(HTTPStatus.BAD_GATEWAY),
            int(HTTPStatus.SERVICE_UNAVAILABLE),
            int(HTTPStatus.GATEWAY_TIMEOUT),
        }:
            return True
        if 400 <= status_code < 500:
            return False
        if status_code >= 500:
            return True

    if any(marker in normalized_text for marker in _RETRYABLE_MESSAGE_MARKERS):
        return True

    return True


def build_embedding_provider_error(
    *,
    message: str,
    status_code: int | None = None,
    code: str | None = None,
    request_id: str | None = None,
    retryable: bool | None = None,
) -> EmbeddingProviderError:
    """Create a normalized embedding error with provider metadata."""
    resolved_retryable = (
        retryable
        if retryable is not None
        else _is_retryable_provider_failure(status_code=status_code, code=code, message=message)
    )

    details: list[str] = []
    if status_code is not None:
        details.append(f"status={status_code}")
    if code:
        details.append(f"code={code}")
    if request_id:
        details.append(f"request_id={request_id}")

    detail_suffix = f" ({', '.join(details)})" if details else ""
    return EmbeddingProviderError(
        f"DashScope embedding request failed{detail_suffix}: {message}",
        retryable=resolved_retryable,
        status_code=status_code,
        code=code,
        request_id=request_id,
    )


def _coerce_embedding(
    value: object,
    *,
    expected_dimension: int | None = None,
) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EmbeddingProviderError(
            "DashScope embedding payload was malformed",
            retryable=True,
        )

    embedding = [float(item) for item in value]
    if expected_dimension is not None and len(embedding) != expected_dimension:
        raise EmbeddingProviderError(
            f"DashScope embedding dimension mismatch: expected {expected_dimension}, got {len(embedding)}",
            retryable=False,
        )
    return embedding


async def generate_dashscope_embeddings(
    texts: list[str],
    *,
    model_name: str,
    api_key: str,
    batch_size: int,
    text_type: str = "document",
    expected_dimension: int | None = None,
) -> list[list[float]]:
    """Generate embeddings through the DashScope SDK with explicit error handling."""
    if not texts:
        return []

    resolved_batch_size = max(1, min(int(batch_size), int(settings.dashscope_embedding_max_batch_size)))
    indexed_texts = [(index, text) for index, text in enumerate(texts)]
    pending_batches: list[list[tuple[int, str]]] = [
        indexed_texts[start : start + resolved_batch_size]
        for start in range(0, len(indexed_texts), resolved_batch_size)
    ]
    ordered_embeddings: list[list[float] | None] = [None] * len(texts)

    while pending_batches:
        indexed_batch = pending_batches.pop(0)
        batch = [text for _, text in indexed_batch]
        if any(not str(text or "").strip() for text in batch):
            raise ValueError("empty text cannot be embedded")

        try:
            response = await asyncio.to_thread(
                TextEmbedding.call,
                model=model_name,
                input=batch,
                api_key=api_key,
                text_type=text_type,
            )
        except EmbeddingProviderError:
            raise
        except Exception as exc:  # pragma: no cover - defensive network/sdk error normalization
            raise build_embedding_provider_error(message=str(exc)) from exc

        status_code = getattr(response, "status_code", None)
        if status_code != int(HTTPStatus.OK):
            message = str(getattr(response, "message", "") or "unknown provider error")
            code = str(getattr(response, "code", "") or "") or None
            request_id = str(getattr(response, "request_id", "") or "") or None

            if _is_provider_batch_limit_error(
                status_code=int(status_code) if status_code is not None else None,
                code=code,
                message=message,
            ) and len(indexed_batch) > 1:
                midpoint = max(1, len(indexed_batch) // 2)
                pending_batches = [
                    indexed_batch[:midpoint],
                    indexed_batch[midpoint:],
                    *pending_batches,
                ]
                continue

            raise build_embedding_provider_error(
                message=message,
                status_code=int(status_code) if status_code is not None else None,
                code=code,
                request_id=request_id,
            )

        output = getattr(response, "output", None) or {}
        embedding_items = output.get("embeddings") if isinstance(output, dict) else None
        if not isinstance(embedding_items, list):
            raise EmbeddingProviderError(
                "DashScope embedding response did not include embeddings",
                retryable=True,
            )

        batch_embeddings: list[list[float] | None] = [None] * len(indexed_batch)
        for item in embedding_items:
            if not isinstance(item, dict):
                raise EmbeddingProviderError(
                    "DashScope embedding response contained an invalid embedding item",
                    retryable=True,
                )

            text_index = item.get("text_index")
            if not isinstance(text_index, int) or not 0 <= text_index < len(indexed_batch):
                raise EmbeddingProviderError(
                    "DashScope embedding response contained an invalid text index",
                    retryable=True,
                )

            batch_embeddings[text_index] = _coerce_embedding(
                item.get("embedding"),
                expected_dimension=expected_dimension,
            )

        for batch_position, embedding in enumerate(batch_embeddings):
            if embedding is None:
                raise EmbeddingProviderError(
                    "DashScope embedding response was incomplete for the current batch",
                    retryable=True,
                )
            original_index = indexed_batch[batch_position][0]
            ordered_embeddings[original_index] = embedding

    resolved_embeddings: list[list[float]] = []
    for embedding in ordered_embeddings:
        if embedding is None:
            raise EmbeddingProviderError(
                "DashScope embedding response was incomplete for the current request",
                retryable=True,
            )
        resolved_embeddings.append(embedding)

    return resolved_embeddings
