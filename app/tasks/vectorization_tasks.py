"""Asynchronous tasks for question-bank vectorization."""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from celery.exceptions import Retry

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.embedding_utils import generate_dashscope_embeddings, is_retryable_task_exception
from app.core.log_config import get_logger
from app.core.redis import redis_client
from app.models.engine import get_celery_session, init_db_engine
from app.models.enums import JobStatus
from app.repositories.question_repo import (
    QuestionRepository,
    VectorizationJobRepository,
    compute_embedding_text_hash,
)
from app.tasks.async_runner import run_coroutine_sync

logger = get_logger(__name__)

VECTORIZATION_LOCK_KEY = "vectorization:lock"
VECTORIZATION_LOCK_TIMEOUT = 6 * 60 * 60


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run coroutine in dedicated async runner loop."""
    return run_coroutine_sync(coro)


def _serialize_embedding(embedding: list[float]) -> str:
    return f"[{','.join(str(float(value)) for value in embedding)}]"


def _question_needs_vectorization(question: Any) -> bool:
    question_text = str(getattr(question, "question_text", "") or "")
    expected_hash = compute_embedding_text_hash(question_text)
    current_hash = getattr(question, "embedding_text_hash", None)
    return bool(
        getattr(question, "is_dirty", True)
        or getattr(question, "question_embedding", None) is None
        or current_hash != expected_hash
    )


async def _generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    return await generate_dashscope_embeddings(
        texts,
        model_name=settings.retrieval_embedding_model,
        api_key=settings.dashscope_api_key,
        batch_size=settings.retrieval_embedding_batch_size,
        text_type="document",
        expected_dimension=settings.retrieval_embedding_dimension,
    )


async def _build_embedding_payloads(questions: list[Any]) -> list[dict[str, Any]]:
    if not questions:
        return []

    texts = [str(question.question_text or "").strip() for question in questions]
    embeddings = await _generate_embeddings_batch(texts)
    vectorized_at = datetime.now(UTC)

    return [
        {
            "question_id": question.id,
            "embedding": _serialize_embedding(embedding),
            "embedding_text_hash": compute_embedding_text_hash(question.question_text),
            "vectorized_at": vectorized_at,
        }
        for question, embedding in zip(questions, embeddings, strict=True)
    ]


async def _refresh_vectorization_locks(job_id_str: str) -> None:
    job_lock_key = f"{VECTORIZATION_LOCK_KEY}:{job_id_str}"
    await redis_client.set(VECTORIZATION_LOCK_KEY, "1", ex=VECTORIZATION_LOCK_TIMEOUT)
    await redis_client.set(job_lock_key, "1", ex=VECTORIZATION_LOCK_TIMEOUT)


async def _release_vectorization_locks(job_id_str: str, *, release_global_lock: bool) -> None:
    await redis_client.delete(f"{VECTORIZATION_LOCK_KEY}:{job_id_str}")
    if release_global_lock:
        await redis_client.delete(VECTORIZATION_LOCK_KEY)


@celery_app.task(
    bind=True,
    name="app.tasks.vectorization_tasks.vectorize_question",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def vectorize_question(self: Any, question_id_str: str, job_id_str: str | None = None) -> dict[str, Any]:
    """Vectorize a single question for compatibility with legacy queues/manual runs."""
    question_id = UUID(question_id_str)
    job_id = UUID(job_id_str) if job_id_str else None
    init_db_engine()

    async def run_vectorization() -> dict[str, Any]:
        async with get_celery_session() as session:
            question_repo = QuestionRepository(session)
            job_repo = VectorizationJobRepository(session) if job_id else None

            question = await question_repo.get_by_id(question_id)
            if not question:
                return {"status": "failed", "question_id": question_id_str, "error": "Question not found"}

            if not _question_needs_vectorization(question):
                if job_repo:
                    assert job_id is not None
                    await job_repo.increment_processed_count(job_id)
                return {"status": "skipped", "question_id": question_id_str, "reason": "already_up_to_date"}

            try:
                payloads = await _build_embedding_payloads([question])
                await question_repo.bulk_store_embeddings(payloads)
                if job_repo:
                    assert job_id is not None
                    await job_repo.increment_processed_count(job_id)

                return {
                    "status": "success",
                    "question_id": question_id_str,
                    "embedding_text_hash": payloads[0]["embedding_text_hash"],
                }
            except Exception as exc:
                logger.error(
                    "Failed to vectorize question",
                    question_id=str(question_id),
                    error=str(exc),
                    exc_info=True,
                )
                retryable = self.request.retries < self.max_retries and is_retryable_task_exception(exc)
                if retryable:
                    raise self.retry(exc=exc, countdown=60 * (2**self.request.retries)) from exc
                raise

    return cast(dict[str, Any], _run_async(run_vectorization()))


@celery_app.task(
    bind=True,
    name="app.tasks.vectorization_tasks.batch_vectorize",
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def batch_vectorize(
    self: Any,
    job_id_str: str,
    only_dirty: bool = True,
    batch_size: int = 10,
) -> dict[str, Any]:
    """Process the full vectorization job in a single paged task."""
    job_id = UUID(job_id_str)
    init_db_engine()

    async def run_batch() -> dict[str, Any]:
        job_lock_key = f"{VECTORIZATION_LOCK_KEY}:{job_id_str}"
        job_lock_acquired = False
        release_global_lock = False
        processed_questions = 0
        total_questions = 0
        effective_batch_size = max(1, min(int(batch_size or settings.retrieval_embedding_batch_size), 100))
        last_created_at: datetime | None = None
        last_id: UUID | None = None

        try:
            job_lock_acquired = bool(await redis_client.set(job_lock_key, "1", nx=True, ex=VECTORIZATION_LOCK_TIMEOUT))
            if not job_lock_acquired:
                async with get_celery_session() as session:
                    existing_job = await VectorizationJobRepository(session).get_by_id(job_id)
                    if existing_job and existing_job.status == JobStatus.SUCCESS:
                        await _release_vectorization_locks(job_id_str, release_global_lock=True)
                        return {
                            "status": "success",
                            "job_id": job_id_str,
                            "total": int(existing_job.total_questions or 0),
                            "processed": int(existing_job.processed_questions or 0),
                            "skipped": True,
                        }

                logger.warning("Vectorization job is already locked, retrying", job_id=job_id_str)
                raise self.retry(countdown=10)

            await _refresh_vectorization_locks(job_id_str)

            async with get_celery_session() as session:
                question_repo = QuestionRepository(session)
                job_repo = VectorizationJobRepository(session)

                existing_job = await job_repo.get_by_id(job_id)
                if not existing_job:
                    release_global_lock = True
                    raise ValueError(f"Vectorization job {job_id} not found")

                if existing_job.status == JobStatus.SUCCESS:
                    release_global_lock = True
                    return {
                        "status": "success",
                        "job_id": job_id_str,
                        "total": int(existing_job.total_questions or 0),
                        "processed": int(existing_job.processed_questions or 0),
                        "skipped": True,
                    }

                total_questions = await question_repo.count_vectorization_candidates(only_dirty=only_dirty)

                if total_questions == 0:
                    await job_repo.update_status(
                        job_id,
                        status=JobStatus.SUCCESS,
                        progress=100,
                        total_questions=0,
                        processed_questions=0,
                        error_message=None,
                    )
                    release_global_lock = True
                    return {"status": "success", "job_id": job_id_str, "total": 0, "processed": 0}

                await job_repo.update_status(
                    job_id,
                    status=JobStatus.RUNNING,
                    progress=0,
                    total_questions=total_questions,
                    processed_questions=0,
                    error_message=None,
                )

            while processed_questions < total_questions:
                async with get_celery_session() as batch_session:
                    question_repo = QuestionRepository(batch_session)
                    job_repo = VectorizationJobRepository(batch_session)

                    page = await question_repo.list_vectorization_candidate_page(
                        only_dirty=only_dirty,
                        limit=effective_batch_size,
                        last_created_at=last_created_at,
                        last_id=last_id,
                    )
                    page_ids = [question_id for question_id, _ in page]
                    if not page_ids:
                        break

                    questions = await question_repo.get_by_ids(page_ids)
                    questions_to_vectorize = [
                        question for question in questions if _question_needs_vectorization(question)
                    ]

                    if questions_to_vectorize:
                        payloads = await _build_embedding_payloads(questions_to_vectorize)
                        await question_repo.bulk_store_embeddings(payloads)

                    processed_questions += len(page_ids)
                    last_id, last_created_at = page[-1][0], page[-1][1]
                    progress = min(100, int(processed_questions * 100 / total_questions))
                    await job_repo.update_status(
                        job_id,
                        progress=progress,
                        processed_questions=processed_questions,
                        error_message=None,
                    )

                await _refresh_vectorization_locks(job_id_str)

            async with get_celery_session() as session:
                await VectorizationJobRepository(session).update_status(
                    job_id,
                    status=JobStatus.SUCCESS,
                    progress=100,
                    total_questions=total_questions,
                    processed_questions=processed_questions,
                    error_message=None,
                )

            release_global_lock = True
            logger.info(
                "Vectorization batch completed",
                job_id=job_id_str,
                total_questions=total_questions,
                processed_questions=processed_questions,
                batch_size=effective_batch_size,
            )
            return {
                "status": "success",
                "job_id": job_id_str,
                "total": total_questions,
                "processed": processed_questions,
            }
        except Retry:
            raise
        except Exception as exc:
            logger.error("Vectorization batch failed", job_id=job_id_str, error=str(exc), exc_info=True)

            async with get_celery_session() as session:
                job_repo = VectorizationJobRepository(session)
                retryable = self.request.retries < self.max_retries and is_retryable_task_exception(exc)
                await job_repo.update_status(
                    job_id,
                    status=JobStatus.PENDING if retryable else JobStatus.FAILED,
                    progress=min(99, int(processed_questions * 100 / total_questions)) if total_questions else 0,
                    total_questions=total_questions or None,
                    processed_questions=processed_questions,
                    error_message=str(exc),
                )
                if not retryable:
                    release_global_lock = True

            if retryable:
                raise self.retry(exc=exc, countdown=60 * (2**self.request.retries)) from exc
            raise
        finally:
            if job_lock_acquired:
                await _release_vectorization_locks(job_id_str, release_global_lock=release_global_lock)

    return cast(dict[str, Any], _run_async(run_batch()))


@celery_app.task(name="app.tasks.vectorization_tasks.finalize_batch")
def finalize_batch(results: list[dict[str, Any]] | None, job_id_str: str) -> dict[str, Any]:
    """Finalize legacy chord-based jobs and release vectorization locks."""
    job_id = UUID(job_id_str)
    init_db_engine()

    async def finalize() -> dict[str, Any]:
        normalized_results = list(results or [])
        success_count = sum(1 for item in normalized_results if item and item.get("status") == "success")
        skipped_count = sum(1 for item in normalized_results if item and item.get("status") == "skipped")
        failed_count = max(0, len(normalized_results) - success_count - skipped_count)
        error_message = f"{failed_count} questions failed to vectorize" if failed_count > 0 else None
        final_status = JobStatus.FAILED if failed_count > 0 else JobStatus.SUCCESS

        async with get_celery_session() as session:
            await VectorizationJobRepository(session).update_status(
                job_id,
                status=final_status,
                progress=100,
                processed_questions=len(normalized_results),
                error_message=error_message,
            )

        await _release_vectorization_locks(job_id_str, release_global_lock=True)
        return {
            "status": "completed",
            "success": success_count,
            "skipped": skipped_count,
            "failed": failed_count,
        }

    return cast(dict[str, Any], _run_async(finalize()))
