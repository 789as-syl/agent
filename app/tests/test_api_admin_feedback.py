from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_feedback import MessageFeedback
from app.models.user import User


@pytest.mark.asyncio
async def test_admin_feedback_list_and_summary(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = Conversation(id=uuid4(), user_id=test_user.id, title="Feedback", is_deleted=False)
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content="Answer with evidence",
        metadata_json={},
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(message)
    await db_session.flush()
    db_session.add(
        MessageFeedback(
            user_id=test_user.id,
            conversation_id=conversation.id,
            message_id=message.id,
            rating="not_helpful",
            evidence_quality="insufficient",
            hallucination_flag=True,
            comment="Evidence too weak",
            metadata_json={},
        )
    )
    await db_session.commit()

    user_response = await client.get("/api/v1/admin/feedback", headers=auth_headers)
    assert user_response.status_code == 403

    list_response = await client.get("/api/v1/admin/feedback", headers=admin_auth_headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["message_preview"] == "Answer with evidence"

    summary_response = await client.get("/api/v1/admin/feedback/summary", headers=admin_auth_headers)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_feedback"] >= 1
    assert summary["hallucination_count"] >= 1
