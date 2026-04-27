from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


async def _create_conversation(db_session: AsyncSession, test_user: User) -> Conversation:
    conv = Conversation(id=uuid4(), user_id=test_user.id, title="Conversation", is_deleted=False)
    db_session.add(conv)
    await db_session.flush()
    return conv


class TestConversationMessages:
    @pytest.mark.asyncio
    async def test_list_messages_exposes_content_blocks_and_omits_legacy_projection_fields(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        message = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content="hello",
            content_blocks_json=[{"type": "text", "text": "hello"}],
            metadata_json={
                "run_id": str(uuid4()),
                "reply_to_message_id": str(uuid4()),
                "thinking_steps": [{"title": "legacy"}],
                "answer_query": "legacy",
                "trace_projection_version": "legacy",
            },
        )
        db_session.add(message)
        await db_session.flush()

        response = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()["items"][0]
        assert "thinking_steps" not in payload
        assert "answer_query" not in payload
        assert "trace_projection_version" not in payload
        assert payload["content_blocks"] == [{"type": "text", "text": "hello"}]
        assert "branch_key" not in payload

    @pytest.mark.asyncio
    async def test_list_messages_normalizes_legacy_execution_trace_fallbacks(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        message = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content="legacy trace",
            metadata_json={
                "run_id": str(uuid4()),
                "reply_to_message_id": str(uuid4()),
                "raw_reasoning": "旧 reasoning",
                "execution_trace": [
                    {
                        "id": "trace-1",
                        "kind": "tool_result",
                        "title": "工具返回：knowledge_retrieval",
                        "status": "completed",
                        "metadata": {
                            "tool_name": "knowledge_retrieval",
                            "tool_input": {"query": "融资风险"},
                            "result_count": 0,
                            "raw_reasoning": "do not expose",
                            "provider_response": {"reasoning_content": "hidden"},
                        },
                    }
                ],
            },
        )
        db_session.add(message)
        await db_session.flush()

        response = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()["items"][0]
        trace_entry = payload["execution_trace"][0]

        assert "raw_reasoning" not in payload
        assert trace_entry["title"] == "工具返回：knowledge_retrieval"
        assert trace_entry["detail"] == "融资风险"
        assert trace_entry["metadata"]["tool_name"] == "knowledge_retrieval"
        serialized = str(payload)
        assert "raw_reasoning" not in serialized
        assert "provider_response" not in serialized
        assert "reasoning_content" not in serialized

    @pytest.mark.asyncio
    async def test_list_messages_sanitizes_protocol_content_blocks(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        message = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content='{"success": false, "tool": "knowledge_retrieval", "payload": {}}自然语言答案',
            content_blocks_json=[
                {"type": "text", "text": "自然语言答案"},
                {"type": "json", "tool": "knowledge_retrieval", "payload": {"error_code": "X"}},
            ],
            metadata_json={"run_id": str(uuid4())},
        )
        db_session.add(message)
        await db_session.flush()

        response = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=auth_headers)

        assert response.status_code == 200
        payload = response.json()["items"][0]
        assert payload["content"] == "自然语言答案"
        assert payload["content_blocks"] == [{"type": "text", "text": "自然语言答案"}]
        serialized = str(payload)
        assert "payload" not in serialized
        assert "knowledge_retrieval" not in serialized
