from __future__ import annotations

from typing import Any

from app.core.exceptions import ValidationError
from app.models.question_bank import QuestionType

CHOICE_OPTION_LABELS: tuple[str, ...] = ("A", "B", "C", "D")
CHOICE_TYPES = {QuestionType.SINGLE, QuestionType.MULTIPLE}


def normalize_question_payload(
    *,
    question_text: str,
    question_type: QuestionType,
    options: list[dict[str, Any]] | None,
    answer: str | None,
    explanation: str | None,
) -> dict[str, Any]:
    normalized_question_text = str(question_text or "").strip()
    if not normalized_question_text:
        raise ValidationError(
            error_code="QUESTION_TEXT_REQUIRED",
            message="Question text is required",
        )

    normalized_explanation = _normalize_optional_text(explanation)

    if question_type in CHOICE_TYPES:
        normalized_options = _normalize_choice_options(options)
        valid_labels = [item["label"] for item in normalized_options]
        normalized_answer = (
            _normalize_single_answer(answer, valid_labels)
            if question_type == QuestionType.SINGLE
            else _normalize_multiple_answer(answer, valid_labels)
        )
    elif question_type == QuestionType.TRUE_FALSE:
        normalized_options = None
        _ensure_options_absent(options, question_type)
        normalized_answer = _normalize_true_false_answer(answer)
    elif question_type == QuestionType.SHORT_ANSWER:
        normalized_options = None
        _ensure_options_absent(options, question_type)
        normalized_answer = _normalize_short_answer(answer)
    else:
        raise ValidationError(
            error_code="QUESTION_TYPE_UNSUPPORTED",
            message=f"Unsupported question type: {question_type}",
        )

    return {
        "question_text": normalized_question_text,
        "question_type": question_type,
        "options": normalized_options,
        "answer": normalized_answer,
        "explanation": normalized_explanation,
    }


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_options_absent(options: list[dict[str, Any]] | None, question_type: QuestionType) -> None:
    if options:
        raise ValidationError(
            error_code="QUESTION_OPTIONS_NOT_ALLOWED",
            message=f"Options are not allowed for question type {question_type.value}",
        )


def _normalize_choice_options(options: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not options:
        raise ValidationError(
            error_code="QUESTION_OPTIONS_REQUIRED",
            message="Choice questions require at least two options",
        )
    if len(options) < 2 or len(options) > len(CHOICE_OPTION_LABELS):
        raise ValidationError(
            error_code="QUESTION_OPTIONS_COUNT_INVALID",
            message="Choice questions must contain between 2 and 4 options",
            details={"min": 2, "max": len(CHOICE_OPTION_LABELS)},
        )

    normalized: list[dict[str, str]] = []
    for item in options:
        label = str(item.get("label") or "").strip().upper()
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValidationError(
                error_code="QUESTION_OPTION_TEXT_REQUIRED",
                message="Option text cannot be empty",
                details={"label": label or None},
            )
        normalized.append({"label": label, "text": text})

    expected_labels = list(CHOICE_OPTION_LABELS[: len(normalized)])
    actual_labels = [item["label"] for item in normalized]
    if actual_labels != expected_labels:
        raise ValidationError(
            error_code="QUESTION_OPTIONS_NON_CONTIGUOUS",
            message="Choice options must use contiguous labels A/B/C/D without gaps",
            details={"expected": expected_labels, "actual": actual_labels},
        )

    return normalized


def _normalize_single_answer(answer: str | None, valid_labels: list[str]) -> str:
    normalized = str(answer or "").strip().upper()
    if normalized not in valid_labels:
        raise ValidationError(
            error_code="QUESTION_ANSWER_INVALID",
            message="Single-choice answer must be one valid option label",
            details={"valid_labels": valid_labels},
        )
    return normalized


def _normalize_multiple_answer(answer: str | None, valid_labels: list[str]) -> str:
    tokens = [token.strip().upper() for token in str(answer or "").split(",") if token.strip()]
    if len(tokens) < 2:
        raise ValidationError(
            error_code="QUESTION_ANSWER_INVALID",
            message="Multiple-choice answer must contain at least two option labels",
            details={"valid_labels": valid_labels},
        )

    unique_tokens = sorted(set(tokens), key=CHOICE_OPTION_LABELS.index)
    invalid_tokens = [token for token in unique_tokens if token not in valid_labels]
    if invalid_tokens:
        raise ValidationError(
            error_code="QUESTION_ANSWER_INVALID",
            message="Multiple-choice answer contains invalid option labels",
            details={"invalid_labels": invalid_tokens, "valid_labels": valid_labels},
        )
    if len(unique_tokens) < 2:
        raise ValidationError(
            error_code="QUESTION_ANSWER_INVALID",
            message="Multiple-choice answer must contain at least two unique option labels",
            details={"valid_labels": valid_labels},
        )
    return ",".join(unique_tokens)


def _normalize_true_false_answer(answer: str | None) -> str:
    normalized = str(answer or "").strip().lower()
    if normalized not in {"true", "false"}:
        raise ValidationError(
            error_code="QUESTION_ANSWER_INVALID",
            message="True/false answer must be 'true' or 'false'",
        )
    return normalized


def _normalize_short_answer(answer: str | None) -> str:
    normalized = str(answer or "").strip()
    if not normalized:
        raise ValidationError(
            error_code="QUESTION_ANSWER_REQUIRED",
            message="Short-answer questions require a text answer",
        )
    return normalized
