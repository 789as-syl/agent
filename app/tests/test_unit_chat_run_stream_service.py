from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_run import ChatRun
from app.models.enums import RunStatus
from app.schemas.sse_event import (
    DoneData,
    FinalAnswerData,
    GenerationDeltaData,
    HITLRequestedData,
    ReasoningDeltaData,
    SSEEvent,
)
from app.services.chat_run_stream_service import ChatRunStreamService


class _FakeNativeRunner:
    async def run(
        self,
        *,
        request_id: str,
        run_id,
        conversation_id: str,
        user_id: str,
        query: str,
        pending_resume_value: dict[str, Any] | None = None,
        should_interrupt=None,
    ):
        del run_id, user_id, query, pending_resume_value, should_interrupt
        yield SSEEvent.create_event(
            event_type="generation_delta",
            request_id=request_id,
            conversation_id=conversation_id,
            step=1,
            trace_data=GenerationDeltaData(delta="hel", accumulated="hel"),
        )
        yield SSEEvent.create_event(
            event_type="reasoning_delta",
            request_id=request_id,
            conversation_id=conversation_id,
            step=2,
            trace_data=ReasoningDeltaData(delta="thinking", accumulated="thinking"),
        )
        yield SSEEvent.create_event(
            event_type="final_answer",
            request_id=request_id,
            conversation_id=conversation_id,
            step=3,
            trace_data=FinalAnswerData(answer="hello", content_blocks=None),
        )
        yield SSEEvent.create_event(
            event_type="done",
            request_id=request_id,
            conversation_id=conversation_id,
            step=4,
            trace_data=DoneData(total_steps=4, duration_ms=1, success=True),
            is_final=True,
        )


class _FakeHITLRunner:
    async def run(
        self,
        *,
        request_id: str,
        run_id,
        conversation_id: str,
        user_id: str,
        query: str,
        pending_resume_value: dict[str, Any] | None = None,
        should_interrupt=None,
    ):
        del run_id, user_id, query, pending_resume_value, should_interrupt
        yield SSEEvent.create_event(
            event_type="generation_delta",
            request_id=request_id,
            conversation_id=conversation_id,
            step=1,
            trace_data=GenerationDeltaData(delta="need ", accumulated="need "),
        )
        yield SSEEvent.create_event(
            event_type="hitl_requested",
            request_id=request_id,
            conversation_id=conversation_id,
            step=2,
            trace_data=HITLRequestedData(kind="input", prompt="which file?", allowed_actions=["respond"]),
        )


class _FakePubSub:
    async def subscribe(self, *_args) -> None:
        return None

    async def get_message(self, **_kwargs):
        await asyncio.sleep(0)
        return None

    async def unsubscribe(self, *_args) -> None:
        return None

    async def close(self) -> None:
        return None


class _FakeRedisClient:
    def pubsub(self) -> _FakePubSub:
        return _FakePubSub()

    async def get(self, *_args) -> None:
        return None


class _FakePersistenceService:
    last_instance: _FakePersistenceService | None = None

    def __init__(self, **_kwargs) -> None:
        self.calls: list[tuple[str, Any]] = []
        _FakePersistenceService.last_instance = self

    async def mark_running(self) -> None:
        self.calls.append(("mark_running", None))

    async def append_event(self, event: SSEEvent) -> None:
        self.calls.append(("append_event", event.event_type))

    async def append_events(self, events: list[SSEEvent]) -> None:
        self.calls.append(("append_events", [event.event_type for event in events]))

    async def persist_hitl_requested(self, event: SSEEvent) -> None:
        self.calls.append(("persist_hitl_requested", event.event_type))

    async def persist_terminal_success(self, event: SSEEvent) -> None:
        self.calls.append(("persist_terminal_success", event.event_type))

    async def persist_terminal_error(self, event: SSEEvent) -> None:
        self.calls.append(("persist_terminal_error", event.event_type))

    async def clear_pending_resume(self) -> None:
        self.calls.append(("clear_pending_resume", None))

    async def handle_error_event(self, event: SSEEvent) -> None:
        self.calls.append(("handle_error_event", event.event_type))

    async def mark_success(self) -> None:
        self.calls.append(("mark_success", None))


@pytest.mark.asyncio
async def test_stream_service_flushes_buffered_deltas_before_terminal_events(monkeypatch) -> None:
    monkeypatch.setattr("app.services.chat_run_stream_service.redis_client", _FakeRedisClient())
    monkeypatch.setattr(
        "app.services.chat_run_stream_service.RunStreamPersistenceService",
        _FakePersistenceService,
    )

    service = ChatRunStreamService(
        session=cast(AsyncSession, SimpleNamespace()),
        session_factory=lambda: cast(AsyncSession, SimpleNamespace()),
        agent_factory=lambda _session: _FakeNativeRunner(),
    )
    run = ChatRun(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        query="hello",
        status=RunStatus.PENDING,
        shell_state_json={},
    )

    handle = await service.prepare_stream(
        run=run,
        conversation_id=run.conversation_id,
        user_id=run.user_id,
    )
    chunks = [chunk async for chunk in handle.event_stream]

    persistence = _FakePersistenceService.last_instance

    assert persistence is not None
    assert len(chunks) == 4
    assert persistence.calls == [
        ("mark_running", None),
        ("append_events", ["generation_delta", "reasoning_delta"]),
        ("append_event", "final_answer"),
        ("persist_terminal_success", "done"),
    ]


@pytest.mark.asyncio
async def test_stream_service_persists_hitl_before_emitting_terminal_control_event(monkeypatch) -> None:
    monkeypatch.setattr("app.services.chat_run_stream_service.redis_client", _FakeRedisClient())
    monkeypatch.setattr(
        "app.services.chat_run_stream_service.RunStreamPersistenceService",
        _FakePersistenceService,
    )

    service = ChatRunStreamService(
        session=cast(AsyncSession, SimpleNamespace()),
        session_factory=lambda: cast(AsyncSession, SimpleNamespace()),
        agent_factory=lambda _session: _FakeHITLRunner(),
    )
    run = ChatRun(
        id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        query="hello",
        status=RunStatus.PENDING,
        shell_state_json={},
    )

    handle = await service.prepare_stream(
        run=run,
        conversation_id=run.conversation_id,
        user_id=run.user_id,
    )
    chunks = [chunk async for chunk in handle.event_stream]

    persistence = _FakePersistenceService.last_instance

    assert persistence is not None
    assert len(chunks) == 2
    assert persistence.calls == [
        ("mark_running", None),
        ("append_events", ["generation_delta"]),
        ("persist_hitl_requested", "hitl_requested"),
    ]
