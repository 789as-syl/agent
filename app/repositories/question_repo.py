"""Repositories for question banks, questions, and vectorization jobs."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError
from app.models.enums import JobStatus
from app.models.question_bank import Question, QuestionBank, QuestionType
from app.models.question_knowledge_point import QuestionKnowledgePoint
from app.models.vectorization_job import VectorizationJob

_UNSET: Any = object()


def compute_content_hash(question_text: str, options: list[dict[str, Any]] | None, answer: str | None) -> str:
    """Build a stable SHA-256 hash for core question content."""
    payload = {
        "question_text": question_text,
        "options": sorted(options or [], key=lambda x: x.get("label", "")),
        "answer": answer or "",
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_embedding_text_hash(question_text: str) -> str:
    """Build a stable SHA-256 hash for the actual vectorized question text."""
    normalized = str(question_text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class QuestionBankRepository:
    """Repository for question-bank CRUD used by admin panel."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_banks(self) -> list[tuple[QuestionBank, int]]:
        stmt = (
            select(QuestionBank, func.count(Question.id).label("total_questions"))
            .outerjoin(Question, Question.bank_id == QuestionBank.id)
            .group_by(QuestionBank.id)
            .order_by(QuestionBank.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [(row[0], int(row[1] or 0)) for row in result.all()]

    async def create(self, name: str, description: str | None = None) -> QuestionBank:
        bank = QuestionBank(name=name, description=description)
        self.session.add(bank)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                error_code="QUESTION_BANK_NAME_CONFLICT",
                message="Question bank name already exists",
                details={"name": name},
            ) from exc
        await self.session.refresh(bank)
        return bank

    async def get_by_id(self, bank_id: uuid.UUID) -> QuestionBank | None:
        result = await self.session.execute(select(QuestionBank).where(QuestionBank.id == bank_id))
        return result.scalar_one_or_none()

    async def update(
        self,
        bank_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> QuestionBank | None:
        bank = await self.get_by_id(bank_id)
        if not bank:
            return None

        if name is not None:
            bank.name = name
        if description is not None:
            bank.description = description

        self.session.add(bank)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                error_code="QUESTION_BANK_NAME_CONFLICT",
                message="Question bank name already exists",
                details={"name": name},
            ) from exc
        await self.session.refresh(bank)
        return bank

    async def count_questions(self, bank_id: uuid.UUID) -> int:
        result = await self.session.execute(select(func.count(Question.id)).where(Question.bank_id == bank_id))
        return int(result.scalar() or 0)

    async def delete(self, bank_id: uuid.UUID) -> bool:
        result = await self.session.execute(delete(QuestionBank).where(QuestionBank.id == bank_id))
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))


class QuestionRepository:
    """Repository for question CRUD, import-upsert, and search helpers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs: Any) -> Question:
        question = Question(**kwargs)
        self.session.add(question)
        await self.session.flush()
        await self.session.refresh(question)
        return question

    async def get_by_id(self, question_id: uuid.UUID, with_links: bool = True) -> Question | None:
        stmt = select(Question).where(Question.id == question_id)
        if with_links:
            stmt = stmt.options(
                selectinload(Question.knowledge_points).selectinload(QuestionKnowledgePoint.knowledge_point)
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_questions(
        self,
        bank_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
        question_type: QuestionType | None = None,
        is_dirty: bool | None = None,
    ) -> tuple[list[Question], int]:
        stmt = select(Question)
        count_stmt = select(func.count()).select_from(Question)

        if bank_id:
            stmt = stmt.where(Question.bank_id == bank_id)
            count_stmt = count_stmt.where(Question.bank_id == bank_id)

        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(Question.question_text.ilike(pattern))
            count_stmt = count_stmt.where(Question.question_text.ilike(pattern))

        if question_type:
            stmt = stmt.where(Question.question_type == question_type)
            count_stmt = count_stmt.where(Question.question_type == question_type)

        if is_dirty is not None:
            stmt = stmt.where(Question.is_dirty.is_(is_dirty))
            count_stmt = count_stmt.where(Question.is_dirty.is_(is_dirty))

        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(Question.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def count_vectorized_questions(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Question).where(
                Question.question_embedding.is_not(None),
                Question.is_dirty.is_(False),
                Question.embedding_text_hash.is_not(None),
            )
        )
        return int(result.scalar() or 0)

    async def update(self, question_id: uuid.UUID, **kwargs: Any) -> Question | None:
        question = await self.get_by_id(question_id)
        if not question:
            return None

        if any(field in kwargs for field in {"question_text", "options", "answer"}):
            next_question_text = str(kwargs.get("question_text", question.question_text) or "").strip()
            next_options = kwargs.get("options", question.options)
            next_answer = kwargs.get("answer", question.answer)
            kwargs["content_hash"] = compute_content_hash(
                next_question_text,
                next_options,
                next_answer,
            )
            if next_question_text != question.question_text:
                kwargs["is_dirty"] = True
                kwargs["question_embedding"] = None
                kwargs["embedding_text_hash"] = None
                kwargs["vectorized_at"] = None

        for key, value in kwargs.items():
            if hasattr(question, key):
                setattr(question, key, value)

        self.session.add(question)
        await self.session.flush()
        await self.session.refresh(question)
        return question

    async def delete(self, question_id: uuid.UUID) -> bool:
        result = await self.session.execute(delete(Question).where(Question.id == question_id))
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def upsert_by_external_id_or_hash(
        self,
        bank_id: uuid.UUID,
        external_id: str | None,
        content_hash: str,
        **kwargs: Any,
    ) -> tuple[Question, bool, bool]:
        if external_id:
            question = await self._find_by_external_id(bank_id, external_id)
            if question:
                await self._update_question(question, **kwargs)
                return question, False, True

        question = await self._find_by_content_hash(bank_id, content_hash)
        if question:
            return question, False, False

        created = await self._create_question(bank_id, external_id, content_hash, **kwargs)
        return created, True, False

    async def _find_by_external_id(self, bank_id: uuid.UUID, external_id: str) -> Question | None:
        result = await self.session.execute(
            select(Question).where(Question.bank_id == bank_id, Question.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def _find_by_content_hash(self, bank_id: uuid.UUID, content_hash: str) -> Question | None:
        result = await self.session.execute(
            select(Question).where(Question.bank_id == bank_id, Question.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def _create_question(
        self,
        bank_id: uuid.UUID,
        external_id: str | None,
        content_hash: str,
        **kwargs: Any,
    ) -> Question:
        question = Question(
            bank_id=bank_id,
            external_id=external_id,
            content_hash=content_hash,
            is_dirty=True,
            **kwargs,
        )
        self.session.add(question)
        await self.session.flush()
        await self.session.refresh(question)
        return question

    async def _update_question(self, question: Question, **kwargs: Any) -> None:
        if any(field in kwargs for field in {"question_text", "options", "answer"}):
            question_text = kwargs.get("question_text", question.question_text)
            options = kwargs.get("options", question.options)
            answer = kwargs.get("answer", question.answer)
            kwargs["content_hash"] = compute_content_hash(question_text, options, answer)
            if str(question_text).strip() != question.question_text:
                kwargs["is_dirty"] = True
                kwargs["question_embedding"] = None
                kwargs["embedding_text_hash"] = None
                kwargs["vectorized_at"] = None

        for key, value in kwargs.items():
            if hasattr(question, key):
                setattr(question, key, value)

        self.session.add(question)
        await self.session.flush()
        await self.session.refresh(question)

    async def get_dirty_questions(self, bank_id: uuid.UUID | None = None, limit: int = 100) -> list[Question]:
        stmt = (
            select(Question)
            .where(
                or_(
                    Question.is_dirty.is_(True),
                    Question.question_embedding.is_(None),
                    Question.embedding_text_hash.is_(None),
                )
            )
            .order_by(Question.created_at.asc())
            .limit(limit)
        )
        if bank_id:
            stmt = stmt.where(Question.bank_id == bank_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _build_vectorization_candidate_condition(only_dirty: bool) -> Any | None:
        if not only_dirty:
            return None
        return or_(
            Question.is_dirty.is_(True),
            Question.question_embedding.is_(None),
            Question.embedding_text_hash.is_(None),
        )

    async def count_vectorization_candidates(self, only_dirty: bool = True) -> int:
        stmt = select(func.count()).select_from(Question)
        candidate_condition = self._build_vectorization_candidate_condition(only_dirty)
        if candidate_condition is not None:
            stmt = stmt.where(candidate_condition)
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_vectorization_candidate_ids(
        self,
        only_dirty: bool = True,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[uuid.UUID]:
        stmt = select(Question.id)
        candidate_condition = self._build_vectorization_candidate_condition(only_dirty)
        if candidate_condition is not None:
            stmt = stmt.where(candidate_condition)
        stmt = stmt.order_by(Question.created_at.asc(), Question.id.asc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self.session.execute(stmt)).fetchall()
        return [row.id for row in rows]

    async def list_vectorization_candidate_page(
        self,
        *,
        only_dirty: bool = True,
        limit: int = 100,
        last_created_at: datetime | None = None,
        last_id: uuid.UUID | None = None,
    ) -> list[tuple[uuid.UUID, datetime]]:
        stmt = select(Question.id, Question.created_at)
        candidate_condition = self._build_vectorization_candidate_condition(only_dirty)
        if candidate_condition is not None:
            stmt = stmt.where(candidate_condition)

        if last_created_at is not None and last_id is not None:
            stmt = stmt.where(
                or_(
                    Question.created_at > last_created_at,
                    and_(Question.created_at == last_created_at, Question.id > last_id),
                )
            )

        stmt = stmt.order_by(Question.created_at.asc(), Question.id.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).fetchall()
        return [(row.id, row.created_at) for row in rows]

    async def get_by_ids(self, question_ids: list[uuid.UUID]) -> list[Question]:
        if not question_ids:
            return []
        result = await self.session.execute(select(Question).where(Question.id.in_(question_ids)))
        records = {question.id: question for question in result.scalars().all()}
        return [records[question_id] for question_id in question_ids if question_id in records]

    async def mark_clean(
        self,
        question_id: uuid.UUID,
        *,
        embedding_text_hash: str | None = None,
        vectorized_at: datetime | None = None,
    ) -> bool:
        values: dict[str, Any] = {"is_dirty": False}
        if embedding_text_hash is not None:
            values["embedding_text_hash"] = embedding_text_hash
        if vectorized_at is not None:
            values["vectorized_at"] = vectorized_at
        result = await self.session.execute(
            update(Question).where(Question.id == question_id).values(**values)
        )
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def bulk_store_embeddings(self, payloads: list[dict[str, Any]]) -> int:
        if not payloads:
            return 0

        stmt = text(
            """
            UPDATE questions
            SET question_embedding = CAST(:embedding AS vector),
                embedding_text_hash = :embedding_text_hash,
                vectorized_at = :vectorized_at,
                is_dirty = FALSE,
                updated_at = NOW()
            WHERE id = :question_id
            """
        )
        params = [
            {
                "question_id": payload["question_id"],
                "embedding": payload["embedding"],
                "embedding_text_hash": payload["embedding_text_hash"],
                "vectorized_at": payload["vectorized_at"],
            }
            for payload in payloads
        ]
        result = await self.session.execute(stmt, params)
        await self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    async def bulk_update_dirty_status(self, question_ids: list[uuid.UUID], is_dirty: bool) -> int:
        if not question_ids:
            return 0
        result = await self.session.execute(
            update(Question).where(Question.id.in_(question_ids)).values(is_dirty=is_dirty)
        )
        await self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    async def link_knowledge_points(
        self,
        question_id: uuid.UUID,
        knowledge_point_ids: list[uuid.UUID],
        relevance_weight: float = 1.0,
    ) -> list[QuestionKnowledgePoint]:
        await self.session.execute(
            delete(QuestionKnowledgePoint).where(QuestionKnowledgePoint.question_id == question_id)
        )

        links = [
            QuestionKnowledgePoint(
                question_id=question_id,
                knowledge_point_id=kp_id,
                relevance_weight=relevance_weight,
            )
            for kp_id in knowledge_point_ids
        ]

        if links:
            self.session.add_all(links)
            await self.session.flush()

        return links

    async def delete_knowledge_point_link(self, question_id: uuid.UUID, knowledge_point_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(QuestionKnowledgePoint).where(
                QuestionKnowledgePoint.question_id == question_id,
                QuestionKnowledgePoint.knowledge_point_id == knowledge_point_id,
            )
        )
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def get_knowledge_point_mapping(self, question_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
        if not question_ids:
            return {}

        stmt = select(
            QuestionKnowledgePoint.question_id,
            QuestionKnowledgePoint.knowledge_point_id,
            QuestionKnowledgePoint.relevance_weight,
        ).where(QuestionKnowledgePoint.question_id.in_(question_ids))

        rows = (await self.session.execute(stmt)).fetchall()

        mapping: dict[uuid.UUID, list[dict]] = {}
        for row in rows:
            mapping.setdefault(row.question_id, []).append(
                {
                    "knowledge_point_id": row.knowledge_point_id,
                    "relevance_weight": row.relevance_weight,
                }
            )
        return mapping

    async def vector_search(
        self,
        embedding: list[float],
        top_k: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[dict]:
        if not embedding:
            return []
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"
        max_distance = max(0.0, 1 - float(similarity_threshold))

        stmt = text(
            """
            SELECT
                q.id AS question_id,
                q.question_text,
                q.question_type,
                q.options,
                q.answer,
                q.explanation,
                q.question_embedding <=> CAST(:embedding AS vector) AS distance,
                1 - (q.question_embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM questions q
            WHERE q.question_embedding IS NOT NULL
              AND q.is_dirty = FALSE
              AND q.embedding_text_hash IS NOT NULL
              AND q.question_embedding <=> CAST(:embedding AS vector) <= :max_distance
            ORDER BY q.question_embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        )

        rows = (
            await self.session.execute(
                stmt,
                {
                    "embedding": embedding_str,
                    "top_k": top_k,
                    "max_distance": max_distance,
                },
            )
        ).fetchall()

        return [
            {
                "question_id": row.question_id,
                "question_text": row.question_text,
                "question_type": row.question_type,
                "options": row.options,
                "answer": row.answer,
                "explanation": row.explanation,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def keyword_search(self, query: str, top_k: int = 10) -> list[dict]:
        stmt = text(
            """
            SELECT
                q.id AS question_id,
                q.question_text,
                q.question_type,
                q.options,
                q.answer,
                q.explanation,
                paradedb.score(q.id) AS score
            FROM questions q
            WHERE q.id @@@ :query
              AND q.is_dirty = FALSE
            ORDER BY score DESC
            LIMIT :top_k
            """
        )

        rows = (await self.session.execute(stmt, {"query": query, "top_k": top_k})).fetchall()
        return [
            {
                "question_id": row.question_id,
                "question_text": row.question_text,
                "question_type": row.question_type,
                "options": row.options,
                "answer": row.answer,
                "explanation": row.explanation,
                "score": float(row.score),
            }
            for row in rows
        ]


class VectorizationJobRepository:
    """Repository for vectorization-job state tracking."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs: Any) -> VectorizationJob:
        job = VectorizationJob(**kwargs)
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> VectorizationJob | None:
        result = await self.session.execute(select(VectorizationJob).where(VectorizationJob.id == job_id))
        return result.scalar_one_or_none()


    async def list_jobs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: JobStatus | str | None = None,
    ) -> tuple[list[VectorizationJob], int]:
        stmt = select(VectorizationJob)
        count_stmt = select(func.count()).select_from(VectorizationJob)
        if status is not None:
            status_value = status if isinstance(status, JobStatus) else JobStatus(str(status))
            stmt = stmt.where(VectorizationJob.status == status_value)
            count_stmt = count_stmt.where(VectorizationJob.status == status_value)
        total = int((await self.session.execute(count_stmt)).scalar() or 0)
        stmt = stmt.order_by(VectorizationJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus | str | None = None,
        progress: int | None = None,
        total_questions: int | None = None,
        processed_questions: int | None = None,
        celery_task_id: str | None | object = _UNSET,
        error_message: str | None | object = _UNSET,
    ) -> VectorizationJob | None:
        job = await self.get_by_id(job_id)
        if not job:
            return None

        if status is not None:
            status_enum = status if isinstance(status, JobStatus) else JobStatus(str(status))
            job.status = status_enum
            if status_enum == JobStatus.RUNNING and job.started_at is None:
                job.started_at = datetime.now(UTC)
            if status_enum in {JobStatus.SUCCESS, JobStatus.FAILED} and job.finished_at is None:
                job.finished_at = datetime.now(UTC)

        if progress is not None:
            job.progress = progress
        if total_questions is not None:
            job.total_questions = total_questions
        if processed_questions is not None:
            job.processed_questions = processed_questions
        if celery_task_id is not _UNSET:
            job.celery_task_id = cast(str | None, celery_task_id)
        if error_message is not _UNSET:
            job.error_message = cast(str | None, error_message)

        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def increment_processed_count(self, job_id: uuid.UUID) -> None:
        await self.session.execute(
            update(VectorizationJob)
            .where(VectorizationJob.id == job_id)
            .values(
                processed_questions=VectorizationJob.processed_questions + 1,
                progress=func.floor(
                    (VectorizationJob.processed_questions + 1)
                    * 100.0
                    / func.nullif(VectorizationJob.total_questions, 0)
                ),
            )
        )
        await self.session.flush()
