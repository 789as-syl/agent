from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.conversation_memory_service import ConversationMemoryService


async def _create_conversation(db_session: AsyncSession, test_user: User) -> Conversation:
    conv = Conversation(id=uuid4(), user_id=test_user.id, title="Conversation", is_deleted=False)
    db_session.add(conv)
    await db_session.flush()
    return conv


class TestConversationMessages:
    @pytest.mark.asyncio
    async def test_persist_run_messages_stores_client_message_id_on_user_and_assistant(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run_id = uuid4()

        await ConversationMemoryService(db_session).persist_run_messages(
            conversation_id=conv.id,
            query="hello",
            final_answer="answer",
            final_content_blocks=[{"type": "text", "text": "answer"}],
            execution_trace=[],
            reasoning_redacted=False,
            run_id=run_id,
            client_message_id="client-persist-1",
        )

        result = await db_session.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.asc())
        )
        messages = list(result.scalars())
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[0].metadata_json["client_message_id"] == "client-persist-1"
        assert messages[1].metadata_json["client_message_id"] == "client-persist-1"
        assert messages[1].metadata_json["run_id"] == str(run_id)

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
    async def test_list_messages_exposes_client_message_id_from_metadata(
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
            metadata_json={
                "run_id": str(uuid4()),
                "client_message_id": "client-serialize-1",
            },
        )
        db_session.add(message)
        await db_session.flush()

        response = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=auth_headers)

        assert response.status_code == 200
        payload = response.json()["items"][0]
        assert payload["client_message_id"] == "client-serialize-1"

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


    @pytest.mark.asyncio
    async def test_list_messages_preserves_answer_basis_and_structured_evidence_additive_fields(
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
            content="基于课程资料回答",
            metadata_json={
                "run_id": str(uuid4()),
                "execution_trace": [
                    {
                        "id": "trace-kb",
                        "kind": "tool_result",
                        "title": "知识库命中 1 个证据块",
                        "status": "completed",
                        "decision_code": "retrieval_hit",
                        "answer_basis": "knowledge_backed",
                        "retrieval_failed": False,
                        "evidence": [
                            {
                                "source": "knowledge_retrieval",
                                "label": "商业模式画布",
                                "title": "商业模式画布",
                                "snippet": "用于描述价值主张、客户细分和收入来源的结构化工具。",
                                "source_type": "courseware",
                                "locator": "page 12",
                                "evidence_type": "retrieved_chunk",
                            }
                        ],
                        "metadata": {
                            "tool_name": "knowledge_retrieval",
                            "retrieval_failed": False,
                            "payload": {"error_code": "SHOULD_NOT_LEAK"},
                        },
                    }
                ],
            },
        )
        db_session.add(message)
        await db_session.flush()

        response = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=auth_headers)

        assert response.status_code == 200
        trace_entry = response.json()["items"][0]["execution_trace"][0]
        assert trace_entry["answer_basis"] == "knowledge_backed"
        assert trace_entry["evidence"][0]["title"] == "商业模式画布"
        assert trace_entry["evidence"][0]["snippet"] == "用于描述价值主张、客户细分和收入来源的结构化工具。"
        assert trace_entry["evidence"][0]["source_type"] == "courseware"
        assert trace_entry["evidence"][0]["locator"] == "page 12"
        assert trace_entry["evidence"][0]["evidence_type"] == "retrieved_chunk"
        serialized = str(trace_entry)
        assert "retrieval_failed" not in serialized
        assert "SHOULD_NOT_LEAK" not in serialized

    @pytest.mark.asyncio
    async def test_list_messages_keeps_legacy_trace_without_answer_basis_as_additive_fallback(
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
            content="legacy answer",
            metadata_json={
                "run_id": str(uuid4()),
                "execution_trace": [
                    {
                        "id": "legacy-direct",
                        "kind": "decision",
                        "title": "直接回答",
                        "status": "completed",
                        "decision_code": "direct_answer",
                    }
                ],
            },
        )
        db_session.add(message)
        await db_session.flush()

        response = await client.get(f"/api/v1/conversations/{conv.id}/messages", headers=auth_headers)

        assert response.status_code == 200
        trace_entry = response.json()["items"][0]["execution_trace"][0]
        assert trace_entry["decision_code"] == "direct_answer"
        assert trace_entry["answer_basis"] == "direct"
