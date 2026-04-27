"""Chat-run interrupt behavior follows the event-driven stream path."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_run import ChatRun
from app.models.enums import RunStatus
from app.schemas.sse_event import ErrorData, SSEEvent
from app.services.chat_run_stream_service import ChatRunStreamService


class _InterruptingPubSub:
    def __init__(self) -> None:
        self.sent = False

    async def subscribe(self, *_args: Any) -> None:
        return None

    async def get_message(self, **_kwargs: Any) -> dict[str, str] | None:
        await asyncio.sleep(0)
        if self.sent:
            return None
        self.sent = True
        return {"data": "interrupt"}

    async def unsubscribe(self, *_args: Any) -> None:
        return None

    async def close(self) -> None:
        return None


class _InterruptingRedisClient:
    def __init__(self) -> None:
        self.pubsub_instance = _InterruptingPubSub()

    def pubsub(self) -> _InterruptingPubSub:
        return self.pubsub_instance

    async def get(self, *_args: Any) -> None:
        return None


class _InterruptAwareRunner:
    async def run(
        self,
        *,
        request_id: str,
        run_id: Any,
        conversation_id: str,
        user_id: str,
        query: str,
        pending_resume_value: dict[str, Any] | None = None,
        should_interrupt=None,
    ):
        del run_id, user_id, query, pending_resume_value
        assert should_interrupt is not None
        for _ in range(5):
            await asyncio.sleep(0)
            if await should_interrupt():
                yield SSEEvent.create_event(
                    event_type="error",
                    request_id=request_id,
                    conversation_id=conversation_id,
                    step=1,
                    trace_data=ErrorData(
                        error_code="AGENT_INTERRUPTED",
                        error_message="用户已中断",
                        recoverable=True,
                    ),
                    is_final=True,
                )
                return


class _FakePersistenceService:
    last_instance: _FakePersistenceService | None = None

    def __init__(self, **_kwargs: Any) -> None:
        self.calls: list[tuple[str, str | None]] = []
        _FakePersistenceService.last_instance = self

    async def mark_running(self) -> None:
        self.calls.append(("mark_running", None))

    async def append_events(self, events: list[SSEEvent]) -> None:
        self.calls.append(("append_events", ",".join(event.event_type for event in events)))

    async def persist_terminal_error(self, event: SSEEvent) -> None:
        self.calls.append(("persist_terminal_error", event.event_type))


@pytest.mark.asyncio
async def test_stream_service_uses_event_driven_interrupt_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.chat_run_stream_service.redis_client", _InterruptingRedisClient())
    monkeypatch.setattr(
        "app.services.chat_run_stream_service.RunStreamPersistenceService",
        _FakePersistenceService,
    )

    service = ChatRunStreamService(
        session=cast(AsyncSession, SimpleNamespace()),
        session_factory=lambda: cast(AsyncSession, SimpleNamespace()),
        agent_factory=lambda _session: _InterruptAwareRunner(),
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
    assert len(chunks) == 1
    assert persistence is not None
    assert persistence.calls == [
        ("mark_running", None),
        ("persist_terminal_error", "error"),
    ]
