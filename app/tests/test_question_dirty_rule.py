"""Tests for question dirty-state behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question_bank import Question, QuestionBank, QuestionType
from app.repositories.question_repo import QuestionRepository, compute_content_hash, compute_embedding_text_hash
from app.schemas.question import QuestionImportItem
from app.services.question_service import QuestionService

_TEST_EMBEDDING = [0.1] * 1024


@pytest.mark.asyncio
async def test_update_question_marks_dirty_only_when_question_text_changes(db_session: AsyncSession):
    bank = QuestionBank(name="dirty-rule-bank", description="dirty rule test")
    db_session.add(bank)
    await db_session.flush()

    question = Question(
        id=uuid4(),
        bank_id=bank.id,
        question_text="原题干",
        question_type=QuestionType.SINGLE,
        options=[{"label": "A", "text": "选项A"}, {"label": "B", "text": "选项B"}],
        answer="A",
        explanation="old",
        content_hash=compute_content_hash(
            "原题干",
            [{"label": "A", "text": "选项A"}, {"label": "B", "text": "选项B"}],
            "A",
        ),
        is_dirty=False,
        question_embedding=_TEST_EMBEDDING,
        embedding_text_hash=compute_embedding_text_hash("原题干"),
        vectorized_at=datetime.now(UTC),
    )
    db_session.add(question)
    await db_session.flush()

    repo = QuestionRepository(db_session)

    unchanged_text = await repo.update(question.id, answer="B")
    assert unchanged_text is not None
    assert unchanged_text.is_dirty is False
    assert unchanged_text.content_hash == compute_content_hash(
        "原题干",
        [{"label": "A", "text": "选项A"}, {"label": "B", "text": "选项B"}],
        "B",
    )

    changed_text = await repo.update(question.id, question_text="新题干")
    assert changed_text is not None
    assert changed_text.is_dirty is True
    assert changed_text.question_embedding is None
    assert changed_text.embedding_text_hash is None
    assert changed_text.vectorized_at is None


@pytest.mark.asyncio
async def test_import_update_keeps_clean_when_question_text_unchanged(db_session: AsyncSession):
    bank = QuestionBank(name="import-dirty-bank", description="import dirty rule test")
    db_session.add(bank)
    await db_session.flush()

    question = Question(
        id=uuid4(),
        bank_id=bank.id,
        external_id="q-1",
        question_text="原题干",
        question_type=QuestionType.SINGLE,
        options=[{"label": "A", "text": "旧选项A"}, {"label": "B", "text": "旧选项B"}],
        answer="A",
        explanation="old",
        content_hash=compute_content_hash(
            "原题干",
            [{"label": "A", "text": "旧选项A"}, {"label": "B", "text": "旧选项B"}],
            "A",
        ),
        is_dirty=False,
        question_embedding=_TEST_EMBEDDING,
        embedding_text_hash=compute_embedding_text_hash("原题干"),
        vectorized_at=datetime.now(UTC),
    )
    db_session.add(question)
    await db_session.flush()

    service = QuestionService(
        question_repo=QuestionRepository(db_session),
        job_repo=SimpleNamespace(),
        kp_repo=None,
    )

    result = await service.import_questions_json(
        bank.id,
        [
            QuestionImportItem.model_validate(
                {
                    "external_id": "q-1",
                    "question_text": "原题干",
                    "question_type": "single",
                    "options": [
                        {"label": "A", "text": "新选项A"},
                        {"label": "B", "text": "新选项B"},
                    ],
                    "answer": "B",
                    "knowledge_point_titles": [],
                }
            )
        ],
    )

    assert result.updated == 1
    updated_question = await QuestionRepository(db_session).get_by_id(question.id)
    assert updated_question is not None
    assert updated_question.is_dirty is False
    assert updated_question.answer == "B"
    assert updated_question.question_embedding is not None
    assert list(updated_question.question_embedding) == _TEST_EMBEDDING
    assert updated_question.embedding_text_hash == compute_embedding_text_hash("原题干")
    assert updated_question.vectorized_at is not None
    assert updated_question.content_hash == compute_content_hash(
        "原题干",
        [{"label": "A", "text": "新选项A"}, {"label": "B", "text": "新选项B"}],
        "B",
    )


@pytest.mark.asyncio
async def test_import_update_marks_dirty_when_question_text_changes(db_session: AsyncSession):
    bank = QuestionBank(name="import-dirty-bank-2", description="import dirty rule test")
    db_session.add(bank)
    await db_session.flush()

    question = Question(
        id=uuid4(),
        bank_id=bank.id,
        external_id="q-2",
        question_text="原题干",
        question_type=QuestionType.SINGLE,
        options=[{"label": "A", "text": "选项A"}, {"label": "B", "text": "选项B"}],
        answer="A",
        explanation="old",
        content_hash=compute_content_hash(
            "原题干",
            [{"label": "A", "text": "选项A"}, {"label": "B", "text": "选项B"}],
            "A",
        ),
        is_dirty=False,
        question_embedding=_TEST_EMBEDDING,
        embedding_text_hash=compute_embedding_text_hash("原题干"),
        vectorized_at=datetime.now(UTC),
    )
    db_session.add(question)
    await db_session.flush()

    service = QuestionService(
        question_repo=QuestionRepository(db_session),
        job_repo=SimpleNamespace(),
        kp_repo=None,
    )

    result = await service.import_questions_json(
        bank.id,
        [
            QuestionImportItem.model_validate(
                {
                    "external_id": "q-2",
                    "question_text": "更新后的题干",
                    "question_type": "single",
                    "options": [
                        {"label": "A", "text": "选项A"},
                        {"label": "B", "text": "选项B"},
                    ],
                    "answer": "A",
                    "knowledge_point_titles": [],
                }
            )
        ],
    )

    assert result.updated == 1
    updated_question = await QuestionRepository(db_session).get_by_id(question.id)
    assert updated_question is not None
    assert updated_question.is_dirty is True
    assert updated_question.question_text == "更新后的题干"
    assert updated_question.question_embedding is None
    assert updated_question.embedding_text_hash is None
    assert updated_question.vectorized_at is None
