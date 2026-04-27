"""Unit tests for canonical question rules."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.models.question_bank import QuestionType
from app.services.question_rules import normalize_question_payload


class TestQuestionRules:
    def test_single_choice_success(self) -> None:
        normalized = normalize_question_payload(
            question_text="题干",
            question_type=QuestionType.SINGLE,
            options=[
                {"label": "A", "text": "选项A"},
                {"label": "B", "text": "选项B"},
            ],
            answer="a",
            explanation="解析",
        )

        assert normalized["answer"] == "A"
        assert normalized["options"][0]["label"] == "A"

    def test_multiple_choice_answer_is_normalized(self) -> None:
        normalized = normalize_question_payload(
            question_text="题干",
            question_type=QuestionType.MULTIPLE,
            options=[
                {"label": "A", "text": "选项A"},
                {"label": "B", "text": "选项B"},
                {"label": "C", "text": "选项C"},
            ],
            answer="c, a, c",
            explanation=None,
        )

        assert normalized["answer"] == "A,C"

    def test_choice_answer_must_match_valid_labels(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            normalize_question_payload(
                question_text="题干",
                question_type=QuestionType.SINGLE,
                options=[
                    {"label": "A", "text": "选项A"},
                    {"label": "B", "text": "选项B"},
                ],
                answer="D",
                explanation=None,
            )

        assert exc_info.value.error_code == "QUESTION_ANSWER_INVALID"

    def test_multiple_choice_requires_at_least_two_answers(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            normalize_question_payload(
                question_text="题干",
                question_type=QuestionType.MULTIPLE,
                options=[
                    {"label": "A", "text": "选项A"},
                    {"label": "B", "text": "选项B"},
                ],
                answer="A",
                explanation=None,
            )

        assert exc_info.value.error_code == "QUESTION_ANSWER_INVALID"

    def test_choice_options_must_be_contiguous(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            normalize_question_payload(
                question_text="题干",
                question_type=QuestionType.SINGLE,
                options=[
                    {"label": "A", "text": "选项A"},
                    {"label": "C", "text": "选项C"},
                ],
                answer="A",
                explanation=None,
            )

        assert exc_info.value.error_code == "QUESTION_OPTIONS_NON_CONTIGUOUS"

    def test_true_false_disallows_options(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            normalize_question_payload(
                question_text="题干",
                question_type=QuestionType.TRUE_FALSE,
                options=[{"label": "A", "text": "对"}, {"label": "B", "text": "错"}],
                answer="true",
                explanation=None,
            )

        assert exc_info.value.error_code == "QUESTION_OPTIONS_NOT_ALLOWED"

    def test_true_false_requires_canonical_answer(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            normalize_question_payload(
                question_text="题干",
                question_type=QuestionType.TRUE_FALSE,
                options=None,
                answer="对",
                explanation=None,
            )

        assert exc_info.value.error_code == "QUESTION_ANSWER_INVALID"

    def test_short_answer_requires_text(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            normalize_question_payload(
                question_text="题干",
                question_type=QuestionType.SHORT_ANSWER,
                options=None,
                answer="   ",
                explanation=None,
            )

        assert exc_info.value.error_code == "QUESTION_ANSWER_REQUIRED"
