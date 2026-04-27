from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question_bank import Question, QuestionBank, QuestionType
from app.models.user import User
from app.repositories.question_repo import compute_content_hash


async def _create_clean_question(db_session: AsyncSession) -> Question:
    bank = QuestionBank(id=uuid4(), name="Learning Bank", description="Learning")
    question = Question(
        id=uuid4(),
        bank_id=bank.id,
        external_id=None,
        content_hash=compute_content_hash("1+1=?", [{"label": "A", "text": "2"}], "A"),
        question_text="1+1=?",
        question_type=QuestionType.SINGLE,
        options=[{"label": "A", "text": "2"}, {"label": "B", "text": "3"}],
        answer="A",
        explanation="1+1=2",
        is_dirty=False,
    )
    db_session.add_all([bank, question])
    await db_session.flush()
    return question


@pytest.mark.asyncio
async def test_learning_loop_creates_session_attempt_wrong_question_and_review_card(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    question = await _create_clean_question(db_session)
    await db_session.commit()

    create_response = await client.post(
        "/api/v1/learning/practice-sessions",
        headers=auth_headers,
        json={"question_ids": [str(question.id)], "title": "Math practice"},
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]
    assert create_response.json()["questions"][0]["id"] == str(question.id)

    submit_response = await client.post(
        f"/api/v1/learning/practice-sessions/{session_id}/submit",
        headers=auth_headers,
        json={"question_id": str(question.id), "answer": "B"},
    )
    assert submit_response.status_code == 200
    assert submit_response.json()["attempt"]["is_correct"] is False
    assert submit_response.json()["wrong_question_updated"] is True

    wrong_response = await client.get("/api/v1/learning/wrong-questions", headers=auth_headers)
    assert wrong_response.status_code == 200
    assert wrong_response.json()["items"][0]["question_id"] == str(question.id)

    mastery_response = await client.get("/api/v1/learning/mastery", headers=auth_headers)
    assert mastery_response.status_code == 200
    assert mastery_response.json()["total"] >= 1

    cards_response = await client.get("/api/v1/learning/review-cards", headers=auth_headers)
    assert cards_response.status_code == 200
    assert cards_response.json()["items"][0]["question_id"] == str(question.id)

    path_response = await client.get("/api/v1/learning/path", headers=auth_headers)
    assert path_response.status_code == 200
    assert path_response.json()["total"] >= 1


@pytest.mark.asyncio
async def test_learning_session_is_user_scoped(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    other_user: User,
) -> None:
    question = await _create_clean_question(db_session)
    await db_session.commit()
    create_response = await client.post(
        "/api/v1/learning/practice-sessions",
        headers=auth_headers,
        json={"question_ids": [str(question.id)]},
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    from app.services.token_service import TokenService

    other_headers = {
        "Authorization": "Bearer " + TokenService.generate_tokens(user_id=other_user.id, phone=other_user.phone)["access_token"]
    }
    denied = await client.get(f"/api/v1/learning/practice-sessions/{session_id}", headers=other_headers)
    assert denied.status_code == 404
