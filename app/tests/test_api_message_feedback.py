from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


@pytest.mark.asyncio
async def test_user_can_upsert_and_get_feedback_for_own_assistant_message(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = Conversation(id=uuid4(), user_id=test_user.id, title="Feedback", is_deleted=False)
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content="Answer for review",
        metadata_json={},
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(message)
    await db_session.commit()

    create_response = await client.post(
        f"/api/v1/feedback/messages/{message.id}",
        headers=auth_headers,
        json={
            "rating": "not_helpful",
            "evidence_quality": "missing",
            "hallucination_flag": True,
            "comment": "Missing citations",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["rating"] == "not_helpful"
    assert payload["hallucination_flag"] is True

    get_response = await client.get(f"/api/v1/feedback/messages/{message.id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["comment"] == "Missing citations"

    update_response = await client.post(
        f"/api/v1/feedback/messages/{message.id}",
        headers=auth_headers,
        json={
            "rating": "helpful",
            "evidence_quality": "sufficient",
            "hallucination_flag": False,
            "comment": "Revised answer works",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["rating"] == "helpful"
    assert updated["hallucination_flag"] is False


@pytest.mark.asyncio
async def test_user_cannot_feedback_other_users_message(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    other_user: User,
) -> None:
    conversation = Conversation(id=uuid4(), user_id=other_user.id, title="Other", is_deleted=False)
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content="Restricted answer",
        metadata_json={},
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(message)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/feedback/messages/{message.id}",
        headers=auth_headers,
        json={"rating": "not_helpful"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_feedback_rejects_user_message_target(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = Conversation(id=uuid4(), user_id=test_user.id, title="Feedback", is_deleted=False)
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="user",
        content="Question text",
        metadata_json={},
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(message)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/feedback/messages/{message.id}",
        headers=auth_headers,
        json={"rating": "helpful"},
    )
    assert response.status_code == 422
