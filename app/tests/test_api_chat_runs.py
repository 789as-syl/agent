from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_run import ChatRun
from app.models.conversation import Conversation
from app.models.enums import RunStatus
from app.models.run_event import RunEvent
from app.models.user import User
from app.schemas.sse_event import (
    DoneData,
    ExecutionTraceData,
    FinalAnswerData,
    GenerationDeltaData,
    HITLRequestedData,
    HITLResolvedData,
    ReasoningDeltaData,
    SSEEvent,
)


class _FakeNativeRunner:
    async def run(
        self,
        *,
        request_id: str,
        run_id: UUID,
        conversation_id: str,
        user_id: str,
        query: str,
        pending_resume_value: dict[str, object] | None = None,
        client_message_id: str | None = None,
        should_interrupt=None,
    ):
        del run_id, user_id, client_message_id, should_interrupt
        step = 1
        if pending_resume_value:
            yield SSEEvent.create_event(
                event_type="hitl_resolved",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=HITLResolvedData(
                    kind="input",
                ),
            )
            step += 1
            yield SSEEvent.create_event(
                event_type="generation_delta",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=GenerationDeltaData(delta="resumed ", accumulated="resumed "),
            )
            step += 1
            yield SSEEvent.create_event(
                event_type="final_answer",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=FinalAnswerData(
                    answer="resumed with app/api/chat_runs.py",
                    content_blocks=[{"type": "text", "text": "resumed with app/api/chat_runs.py"}],
                ),
            )
            step += 1
            yield SSEEvent.create_event(
                event_type="done",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=DoneData(total_steps=step, duration_ms=1, success=True),
                is_final=True,
            )
            return

        if query == "need clarification":
            yield SSEEvent.create_event(
                event_type="hitl_requested",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=HITLRequestedData(
                    kind="input",
                    prompt="which file?",
                    allowed_actions=["respond", "reject"],
                ),
            )
            return

        if query == "out of scope":
            yield SSEEvent.create_event(
                event_type="execution_trace",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=ExecutionTraceData(
                    kind="reasoning",
                    title="识别为非创新创业问题",
                    detail="当前问题超出创新创业问答范围，系统已返回引导说明。",
                    status="completed",
                    metadata={"strategy": "short-circuit", "reason": "out_of_scope"},
                ),
            )
            step += 1
            yield SSEEvent.create_event(
                event_type="final_answer",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=FinalAnswerData(
                    answer="guide message",
                    content_blocks=[{"type": "text", "text": "guide message"}],
                ),
            )
            step += 1
            yield SSEEvent.create_event(
                event_type="done",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=DoneData(total_steps=step, duration_ms=1, success=True),
                is_final=True,
            )
            return

        yield SSEEvent.create_event(
            event_type="generation_delta",
            request_id=request_id,
            conversation_id=conversation_id,
            step=step,
            trace_data=GenerationDeltaData(delta="answer ", accumulated="answer "),
        )
        step += 1
        yield SSEEvent.create_event(
            event_type="reasoning_delta",
            request_id=request_id,
            conversation_id=conversation_id,
            step=step,
            trace_data=ReasoningDeltaData(delta="thinking", accumulated="thinking", source="reasoning_content"),
        )
        step += 1
        yield SSEEvent.create_event(
            event_type="final_answer",
            request_id=request_id,
            conversation_id=conversation_id,
            step=step,
            trace_data=FinalAnswerData(
                answer=f"answer for {query}",
                content_blocks=[{"type": "text", "text": f"answer for {query}"}],
            ),
        )
        step += 1
        yield SSEEvent.create_event(
            event_type="done",
            request_id=request_id,
            conversation_id=conversation_id,
            step=step,
            trace_data=DoneData(total_steps=step, duration_ms=1, success=True),
            is_final=True,
        )


def _fake_agent_factory(_session):
    return _FakeNativeRunner()


def _parse_sse_frames(body: str) -> list[tuple[str, dict]]:
    frames: list[tuple[str, dict]] = []
    for raw_frame in body.strip().split("\n\n"):
        if not raw_frame.strip():
            continue
        event_name: str | None = None
        payload: dict | None = None
        for line in raw_frame.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            if line.startswith("data: "):
                import json

                payload = json.loads(line.removeprefix("data: "))
        if event_name and payload is not None:
            frames.append((event_name, payload))
    return frames


async def _create_conversation(db_session: AsyncSession, test_user: User, title: str = "Test Conv") -> Conversation:
    conv = Conversation(id=uuid4(), user_id=test_user.id, title=title, is_deleted=False)
    db_session.add(conv)
    await db_session.flush()
    return conv


class TestChatRunCreate:
    @pytest.mark.asyncio
    async def test_create_chat_run_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)

        response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs",
            headers=auth_headers,
            json={"query": "What is the capital of France?"},
        )

        assert response.status_code == 201
        data = response.json()
        run = await db_session.scalar(select(ChatRun).where(ChatRun.id == UUID(data["run_id"])))
        assert run is not None
        assert run.shell_state_json == {}
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_chat_run_persists_client_message_id_in_shell_state(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)

        response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs",
            headers=auth_headers,
            json={"query": "What is the capital of France?", "client_message_id": "client-create-1"},
        )

        assert response.status_code == 201
        run = await db_session.scalar(select(ChatRun).where(ChatRun.id == UUID(response.json()["run_id"])))
        assert run is not None
        assert run.shell_state_json == {"client_message_id": "client-create-1"}

    @pytest.mark.asyncio
    async def test_create_chat_run_conflict_when_active_run_exists(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        db_session.add(
            ChatRun(
                id=uuid4(),
                conversation_id=conv.id,
                user_id=test_user.id,
                query="existing",
                status=RunStatus.RUNNING,
                shell_state_json={},
            )
        )
        await db_session.flush()

        response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs",
            headers=auth_headers,
            json={"query": "new request"},
        )

        assert response.status_code == 409
        payload = response.json()
        assert payload["error_code"] == "CONVERSATION_RUN_CONFLICT"
        assert payload["details"]["requested_action"] == "create"


class TestChatRunStatus:
    @pytest.mark.asyncio
    async def test_get_chat_run_returns_runtime_state(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.RUNNING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()

        async def fake_runtime_state(_run):
            from app.api.chat_runs import ChatRunRuntimeState

            return ChatRunRuntimeState(
                hitl=None,
            )

        monkeypatch.setattr("app.api.chat_runs._build_runtime_state", fake_runtime_state)

        response = await client.get(f"/api/v1/conversations/{conv.id}/runs/{run.id}", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["runtime_state"]["hitl"] is None


class TestChatRunEvents:
    @pytest.mark.asyncio
    async def test_get_event_playback_slice(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.SUCCESS,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        event = SSEEvent.create_event(
            event_type="final_answer",
            request_id=str(run.id),
            conversation_id=str(conv.id),
            step=1,
            trace_data=FinalAnswerData(answer="hello", content_blocks=None),
        )
        db_session.add(
            RunEvent(
                run_id=run.id,
                conversation_id=conv.id,
                user_id=test_user.id,
                event_id=event.event_id,
                event_type=event.event_type,
                step=event.step,
                is_final=False,
                event_json=event.model_dump(mode="python"),
            )
        )
        await db_session.commit()

        response = await client.get(f"/api/v1/conversations/{conv.id}/runs/{run.id}/events", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["last_event_id"] == event.event_id
        assert payload["events"][0]["event_type"] == "final_answer"

    @pytest.mark.asyncio
    async def test_stream_execution_trace_event_shape(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.SUCCESS,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        trace_event = SSEEvent.create_event(
            event_type="execution_trace",
            request_id=str(run.id),
            conversation_id=str(conv.id),
            step=1,
            trace_data=ExecutionTraceData(
                kind="tool_call",
                title="调用知识库检索：需要资料证据",
                detail="命中信号：课程资料",
                status="running",
                decision_code="tool_call_knowledge_retrieval",
                tool_name="knowledge_retrieval",
                tool_input={"query": "hello"},
                evidence=[{"source": "classifier", "label": "命中问题信号", "detail": "课程资料"}],
                reasoning_anchor={"start": 0, "end": 6},
            ),
        )
        db_session.add(
            RunEvent(
                run_id=run.id,
                conversation_id=conv.id,
                user_id=test_user.id,
                event_id=trace_event.event_id,
                event_type=trace_event.event_type,
                step=trace_event.step,
                is_final=False,
                event_json=trace_event.model_dump(mode="python"),
            )
        )
        await db_session.commit()

        response = await client.get(f"/api/v1/conversations/{conv.id}/runs/{run.id}/events", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["events"][0]["event_type"] == "execution_trace"
        trace_payload = response.json()["events"][0]["trace_data"]
        assert trace_payload["decision_code"] == "tool_call_knowledge_retrieval"
        assert trace_payload["evidence"][0]["label"] == "命中问题信号"

    @pytest.mark.asyncio
    async def test_get_execution_trace_playback_preserves_answer_basis_and_structured_evidence(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.SUCCESS,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        event = SSEEvent.create_event(
            event_type="execution_trace",
            request_id=str(run.id),
            conversation_id=str(conv.id),
            step=1,
            trace_data=ExecutionTraceData(
                kind="tool_result",
                title="知识库命中 1 个证据块",
                status="completed",
                decision_code="retrieval_hit",
                answer_basis="knowledge_backed",
                evidence=[
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
            ),
        )
        db_session.add(
            RunEvent(
                run_id=run.id,
                conversation_id=conv.id,
                user_id=test_user.id,
                event_id=event.event_id,
                event_type=event.event_type,
                step=event.step,
                is_final=False,
                event_json=event.model_dump(mode="python"),
            )
        )
        await db_session.commit()

        response = await client.get(f"/api/v1/conversations/{conv.id}/runs/{run.id}/events", headers=auth_headers)

        assert response.status_code == 200
        trace_data = response.json()["events"][0]["trace_data"]
        assert trace_data["answer_basis"] == "knowledge_backed"
        assert trace_data["evidence"][0]["title"] == "商业模式画布"
        assert trace_data["evidence"][0]["snippet"] == "用于描述价值主张、客户细分和收入来源的结构化工具。"
        assert trace_data["evidence"][0]["source_type"] == "courseware"
        assert trace_data["evidence"][0]["locator"] == "page 12"
        assert trace_data["evidence"][0]["evidence_type"] == "retrieved_chunk"

    @pytest.mark.asyncio
    async def test_get_reasoning_delta_event_playback(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.SUCCESS,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        event = SSEEvent.create_event(
            event_type="reasoning_delta",
            request_id=str(run.id),
            conversation_id=str(conv.id),
            step=1,
            trace_data=ReasoningDeltaData(delta="分析中", accumulated="分析中", source="reasoning_content"),
        )
        db_session.add(
            RunEvent(
                run_id=run.id,
                conversation_id=conv.id,
                user_id=test_user.id,
                event_id=event.event_id,
                event_type=event.event_type,
                step=event.step,
                is_final=False,
                event_json=event.model_dump(mode="python"),
            )
        )
        await db_session.commit()

        response = await client.get(f"/api/v1/conversations/{conv.id}/runs/{run.id}/events", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["events"][0]["event_type"] == "reasoning_delta"


class TestChatRunStream:
    @pytest.mark.asyncio
    async def test_stream_chat_run_emits_final_answer_and_done(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.PENDING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.commit()
        monkeypatch.setattr("app.api.chat_runs.create_native_agent", _fake_agent_factory)
        monkeypatch.setattr("app.api.chat_runs.get_async_session_factory", lambda: (lambda: db_session))

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.api.chat_runs.ChatRunService.ensure_run_is_active_owner", _noop)

        async with client.stream(
            "GET",
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/stream",
            headers=auth_headers,
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

        assert response.status_code == 200
        assert "event: final_answer" in body
        assert "event: done" in body
        assert "\n\n" in body

    @pytest.mark.asyncio
    async def test_stream_chat_run_replays_events_after_cursor_before_live_events(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.PENDING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        anchor = SSEEvent.create_event(
            event_type="generation_delta",
            request_id=str(run.id),
            conversation_id=str(conv.id),
            step=1,
            trace_data=GenerationDeltaData(delta="old ", accumulated="old "),
        )
        replay = SSEEvent.create_event(
            event_type="reasoning_delta",
            request_id=str(run.id),
            conversation_id=str(conv.id),
            step=2,
            trace_data=ReasoningDeltaData(delta="replay", accumulated="replay"),
        )
        for event in (anchor, replay):
            db_session.add(
                RunEvent(
                    run_id=run.id,
                    conversation_id=conv.id,
                    user_id=test_user.id,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    step=event.step,
                    is_final=False,
                    event_json=event.model_dump(mode="python"),
                )
            )
        await db_session.commit()

        class _SessionContext:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, *_args):
                return None

        monkeypatch.setattr("app.api.chat_runs.create_native_agent", _fake_agent_factory)
        monkeypatch.setattr("app.api.chat_runs.get_async_session_factory", lambda: (lambda: _SessionContext()))

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.api.chat_runs.ChatRunService.ensure_run_is_active_owner", _noop)

        async with client.stream(
            "GET",
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/stream?after_event_id={anchor.event_id}",
            headers=auth_headers,
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

        assert response.status_code == 200
        frames = _parse_sse_frames(body)
        assert frames[0][1]["event_id"] == replay.event_id
        assert frames[0][0] == "reasoning_delta"

    @pytest.mark.asyncio
    async def test_stream_chat_run_emits_incremental_events_before_terminal_events(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.PENDING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.commit()
        monkeypatch.setattr("app.api.chat_runs.create_native_agent", _fake_agent_factory)
        monkeypatch.setattr("app.api.chat_runs.get_async_session_factory", lambda: (lambda: db_session))

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.api.chat_runs.ChatRunService.ensure_run_is_active_owner", _noop)

        async with client.stream(
            "GET",
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/stream",
            headers=auth_headers,
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

        assert response.status_code == 200
        frames = _parse_sse_frames(body)
        event_names = [event_name for event_name, _payload in frames]
        steps = [int(payload["step"]) for _event_name, payload in frames]

        assert event_names == ["generation_delta", "reasoning_delta", "final_answer", "done"]
        assert steps == sorted(steps)

    @pytest.mark.asyncio
    async def test_stream_chat_run_marks_run_success_before_regenerate(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="out of scope",
            status=RunStatus.PENDING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.commit()
        monkeypatch.setattr("app.api.chat_runs.create_native_agent", _fake_agent_factory)
        monkeypatch.setattr("app.api.chat_runs.get_async_session_factory", lambda: (lambda: db_session))

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.api.chat_runs.ChatRunService.ensure_run_is_active_owner", _noop)

        async with client.stream(
            "GET",
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/stream",
            headers=auth_headers,
        ) as response:
            _ = "".join([chunk async for chunk in response.aiter_text()])

        assert response.status_code == 200
        persisted_run = await db_session.scalar(select(ChatRun).where(ChatRun.id == run.id))
        assert persisted_run is not None
        assert persisted_run.status == RunStatus.SUCCESS

        regenerate_response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/regenerate",
            headers=auth_headers,
        )
        assert regenerate_response.status_code == 200

    @pytest.mark.asyncio
    async def test_stream_chat_run_marks_run_success_before_create_follow_up_run(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="out of scope",
            status=RunStatus.PENDING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.commit()
        monkeypatch.setattr("app.api.chat_runs.create_native_agent", _fake_agent_factory)
        monkeypatch.setattr("app.api.chat_runs.get_async_session_factory", lambda: (lambda: db_session))

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.api.chat_runs.ChatRunService.ensure_run_is_active_owner", _noop)

        async with client.stream(
            "GET",
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/stream",
            headers=auth_headers,
        ) as response:
            _ = "".join([chunk async for chunk in response.aiter_text()])

        assert response.status_code == 200
        persisted_run = await db_session.scalar(select(ChatRun).where(ChatRun.id == run.id))
        assert persisted_run is not None
        assert persisted_run.status == RunStatus.SUCCESS

        create_response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs",
            headers=auth_headers,
            json={"query": "new request"},
        )
        assert create_response.status_code == 201

    @pytest.mark.asyncio
    async def test_resume_chat_run_accepts_hitl_decision(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="need clarification",
            status=RunStatus.RUNNING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()

        from app.services.run_resume_service import RunResumeSnapshot

        async def fake_snapshot(_self, _run):
            return RunResumeSnapshot(
                hitl_pending=True,
                hitl_kind="input",
                hitl_prompt="which file?",
                allowed_actions=["respond", "reject"],
                resume_supported=True,
                legacy_checkpoint_detected=False,
                reason=None,
                interrupt_payload={
                    "action_requests": [
                        {"name": "request_human_input", "args": {"prompt": "which file?", "kind": "input"}}
                    ],
                    "review_configs": [{"allowed_decisions": ["edit", "reject"]}],
                },
                action_name="request_human_input",
                action_args={"prompt": "which file?", "kind": "input"},
            )

        async def fake_runtime_state(_run):
            from app.api.chat_runs import ChatRunRuntimeState

            return ChatRunRuntimeState(
                hitl={
                    "pending": True,
                    "kind": "input",
                    "prompt": "which file?",
                    "allowed_actions": ["respond", "reject"],
                },
            )

        monkeypatch.setattr("app.api.chat_runs._build_runtime_state", fake_runtime_state)
        monkeypatch.setattr("app.api.chat_runs.RunResumeService.build_resume_snapshot", fake_snapshot)
        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.api.chat_runs.ChatRunService.ensure_run_is_active_owner", _noop)

        response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/resume",
            headers=auth_headers,
            json={"decision": {"type": "respond", "value": "app/api/chat_runs.py"}},
        )
        assert response.status_code == 200
        await db_session.refresh(run)
        assert run.shell_state_json["pending_resume_value"]["decision_type"] == "respond"
        assert run.shell_state_json["pending_resume_value"]["decision"]["type"] == "edit"


class TestChatRunLineage:
    @pytest.mark.asyncio
    async def test_retry_and_regenerate_preserve_lineage(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv_retry = await _create_conversation(db_session, test_user, title="Retry Conv")
        conv_regen = await _create_conversation(db_session, test_user, title="Regenerate Conv")
        failed_run = ChatRun(
            id=uuid4(),
            conversation_id=conv_retry.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.FAILED,
            shell_state_json={},
        )
        success_run = ChatRun(
            id=uuid4(),
            conversation_id=conv_regen.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.SUCCESS,
            shell_state_json={},
        )
        db_session.add_all([failed_run, success_run])
        await db_session.flush()

        retry_resp = await client.post(
            f"/api/v1/conversations/{conv_retry.id}/runs/{failed_run.id}/retry",
            headers=auth_headers,
        )
        regen_resp = await client.post(
            f"/api/v1/conversations/{conv_regen.id}/runs/{success_run.id}/regenerate",
            headers=auth_headers,
        )

        assert retry_resp.status_code == 200
        retry_run = await db_session.scalar(select(ChatRun).where(ChatRun.id == UUID(retry_resp.json()["run_id"])))
        assert retry_run is not None
        assert retry_run.retry_of_run_id == failed_run.id

        assert regen_resp.status_code == 200
        regen_run = await db_session.scalar(select(ChatRun).where(ChatRun.id == UUID(regen_resp.json()["run_id"])))
        assert regen_run is not None
        assert regen_run.parent_run_id == success_run.id

    @pytest.mark.asyncio
    async def test_retry_and_regenerate_accept_fresh_client_message_ids(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv_retry = await _create_conversation(db_session, test_user, title="Retry Client Id Conv")
        conv_regen = await _create_conversation(db_session, test_user, title="Regen Client Id Conv")
        failed_run = ChatRun(
            id=uuid4(),
            conversation_id=conv_retry.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.FAILED,
            shell_state_json={"client_message_id": "old-client-id"},
        )
        success_run = ChatRun(
            id=uuid4(),
            conversation_id=conv_regen.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.SUCCESS,
            shell_state_json={"client_message_id": "old-regen-id"},
        )
        db_session.add_all([failed_run, success_run])
        await db_session.flush()

        retry_resp = await client.post(
            f"/api/v1/conversations/{conv_retry.id}/runs/{failed_run.id}/retry",
            headers=auth_headers,
            json={"client_message_id": "retry-client-2"},
        )
        regen_resp = await client.post(
            f"/api/v1/conversations/{conv_regen.id}/runs/{success_run.id}/regenerate",
            headers=auth_headers,
            json={"client_message_id": "regen-client-3"},
        )

        assert retry_resp.status_code == 200
        retry_run = await db_session.scalar(select(ChatRun).where(ChatRun.id == UUID(retry_resp.json()["run_id"])))
        assert retry_run is not None
        assert retry_run.shell_state_json == {"client_message_id": "retry-client-2"}

        assert regen_resp.status_code == 200
        regen_run = await db_session.scalar(select(ChatRun).where(ChatRun.id == UUID(regen_resp.json()["run_id"])))
        assert regen_run is not None
        assert regen_run.shell_state_json == {"client_message_id": "regen-client-3"}

    @pytest.mark.asyncio
    async def test_stream_passes_client_message_id_to_runner(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.PENDING,
            shell_state_json={"client_message_id": "stream-client-1"},
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.commit()
        seen: dict[str, str | None] = {}

        class _RecordingRunner(_FakeNativeRunner):
            async def run(self, **kwargs):
                seen["client_message_id"] = kwargs.get("client_message_id")
                async for event in super().run(**kwargs):
                    yield event

        monkeypatch.setattr("app.api.chat_runs.create_native_agent", lambda _session: _RecordingRunner())
        monkeypatch.setattr("app.api.chat_runs.get_async_session_factory", lambda: (lambda: db_session))

        response = await client.get(
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/stream",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert seen["client_message_id"] == "stream-client-1"

    @pytest.mark.asyncio
    async def test_retry_conflicts_when_another_active_run_owns_conversation(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        failed_run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.FAILED,
            shell_state_json={},
        )
        active_run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="active",
            status=RunStatus.RUNNING,
            shell_state_json={},
        )
        db_session.add_all([failed_run, active_run])
        await db_session.flush()

        response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs/{failed_run.id}/retry",
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "CONVERSATION_RUN_CONFLICT"
        assert response.json()["details"]["requested_action"] == "retry"


class TestChatRunInterrupt:
    @pytest.mark.asyncio
    async def test_interrupt_chat_run_publishes_redis_signal(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        monkeypatch,
    ) -> None:
        conv = await _create_conversation(db_session, test_user)
        run = ChatRun(
            id=uuid4(),
            conversation_id=conv.id,
            user_id=test_user.id,
            query="hello",
            status=RunStatus.RUNNING,
            shell_state_json={},
        )
        db_session.add(run)
        await db_session.flush()
        await db_session.commit()

        setex_calls = []
        publish_calls = []

        async def fake_setex(key, ttl, value):
            setex_calls.append((key, ttl, value))
            return True

        async def fake_publish(channel, payload):
            publish_calls.append((channel, payload))
            return 1

        monkeypatch.setattr("app.api.chat_runs.redis_client.setex", fake_setex)
        monkeypatch.setattr("app.api.chat_runs.redis_client.publish", fake_publish)

        response = await client.post(
            f"/api/v1/conversations/{conv.id}/runs/{run.id}/interrupt",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert setex_calls
        assert publish_calls
