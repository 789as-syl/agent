from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


async def _create_conversation(db_session: AsyncSession, user: User) -> Conversation:
    conv = Conversation(id=uuid4(), user_id=user.id, title="Admin Audit", is_deleted=False)
    db_session.add(conv)
    await db_session.flush()
    return conv


class TestAdminConversationMessages:
    @pytest.mark.asyncio
    async def test_admin_message_payload_omits_thinking_steps(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        message = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content="hello",
            metadata_json={
                "reply_to_message_id": str(uuid4()),
                "thinking_steps": [{"title": "legacy"}],
            },
        )
        db_session.add(message)
        await db_session.flush()

        response = await client.get(
            f"/api/v1/admin/users/{test_user.id}/conversations/{conv.id}/messages",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        payload = response.json()["items"][0]
        assert "thinking_steps" not in payload
        assert payload["content"] == "hello"
