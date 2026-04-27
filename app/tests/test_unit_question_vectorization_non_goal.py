"""Non-goal guard tests for question vectorization semantics."""

from __future__ import annotations

from types import SimpleNamespace

from app.repositories.question_repo import compute_embedding_text_hash
from app.tasks import vectorization_tasks


def test_question_needs_vectorization_false_for_clean_and_up_to_date() -> None:
    text = "保持语义不变"
    question = SimpleNamespace(
        question_text=text,
        question_embedding=[0.1, 0.2],
        embedding_text_hash=compute_embedding_text_hash(text),
        is_dirty=False,
    )

    assert vectorization_tasks._question_needs_vectorization(question) is False


def test_question_needs_vectorization_true_when_hash_mismatches() -> None:
    question = SimpleNamespace(
        question_text="hash mismatch",
        question_embedding=[0.1, 0.2],
        embedding_text_hash="outdated-hash",
        is_dirty=False,
    )

    assert vectorization_tasks._question_needs_vectorization(question) is True


def test_question_needs_vectorization_true_when_embedding_missing() -> None:
    text = "缺失 embedding"
    question = SimpleNamespace(
        question_text=text,
        question_embedding=None,
        embedding_text_hash=compute_embedding_text_hash(text),
        is_dirty=False,
    )

    assert vectorization_tasks._question_needs_vectorization(question) is True
