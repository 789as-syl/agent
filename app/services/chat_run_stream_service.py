"""SSE orchestration around the native-only create_agent runner."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.log_config import get_logger
from app.core.redis import build_chat_run_interrupt_channel, build_chat_run_interrupt_flag_key, redis_client
from app.models.chat_run import ChatRun
from app.models.enums import RunStatus
from app.repositories.run_event_repo import RunEventRepository
from app.schemas.sse_event import SSEEvent
from app.services.chat_run_service import ChatRunService, get_run_client_message_id
from app.services.run_event_playback_service import RunEventPlaybackService
from app.services.run_stream_persistence_service import RunStreamPersistenceService

logger = get_logger(__name__)


@dataclass(slots=True)
class ChatRunStreamHandle:
    event_stream: AsyncGenerator[str, None]
    headers: dict[str, str]


class ChatRunStreamService:
    STREAM_BATCH_EVENT_TYPES: frozenset[str] = frozenset({"generation_delta", "reasoning_delta"})
    STREAM_BATCH_SIZE = 4
    STREAM_BATCH_MAX_DELAY_SECONDS = 0.05

    def __init__(
        self,
        *,
        session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession],
        agent_factory: Callable[[AsyncSession], Any],
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.agent_factory = agent_factory

    @staticmethod
    def validate_run_for_stream(run: ChatRun) -> None:
        if run.status == RunStatus.SUCCESS:
            raise ValueError("run already completed")
        if run.status == RunStatus.INTERRUPTED:
            raise ValueError("run interrupted; create a retry run")
        if run.status not in (RunStatus.PENDING, RunStatus.RUNNING):
            raise ValueError(f"invalid run status: {run.status}")

    async def prepare_stream(
        self,
        *,
        run: ChatRun,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        replay_after_event_id: str | None = None,
    ) -> ChatRunStreamHandle:
        persistence_service = RunStreamPersistenceService(
            session_factory=self.session_factory,
            run_id=run.id,
            conversation_id=conversation_id,
            user_id=user_id,
        )
        await persistence_service.mark_running()

        chat_run_service = ChatRunService(self.session)
        pending_resume_value = chat_run_service.consume_pending_resume_value(run)
        client_message_id = get_run_client_message_id(run)
        agent = self.agent_factory(self.session)
        interrupt_event = asyncio.Event()
        interrupt_channel = build_chat_run_interrupt_channel(run.id)
        interrupt_flag_key = build_chat_run_interrupt_flag_key(run.id)

        async def load_replay_events(after_event_id: str) -> list[SSEEvent]:
            async with self.session_factory() as isolated_session:
                playback = RunEventPlaybackService(RunEventRepository(isolated_session))
                playback_slice = await playback.get_slice(run.id, after_event_id=after_event_id)
                return playback_slice.events

        async def event_stream() -> AsyncGenerator[str, None]:
            waiting_for_resume = False
            resume_input_cleared = False
            buffered_events: list[SSEEvent] = []
            buffer_flush_task: asyncio.Task[None] | None = None
            pubsub = redis_client.pubsub()

            async def listen_for_interrupt() -> None:
                try:
                    await pubsub.subscribe(interrupt_channel)
                    if await redis_client.get(interrupt_flag_key):
                        interrupt_event.set()
                        return
                    while not interrupt_event.is_set():
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=1.0,
                        )
                        if message and message.get("data") == "interrupt":
                            interrupt_event.set()
                            return
                        if await redis_client.get(interrupt_flag_key):
                            interrupt_event.set()
                            return
                except Exception as exc:  # pragma: no cover - defensive runtime logging
                    logger.warning("interrupt listener failed", error=str(exc), run_id=str(run.id))
                finally:
                    with suppress(Exception):
                        await pubsub.unsubscribe(interrupt_channel)
                    await pubsub.close()

            interrupt_listener = asyncio.create_task(listen_for_interrupt())

            async def cancel_buffer_flush_task() -> None:
                nonlocal buffer_flush_task
                if buffer_flush_task is None or buffer_flush_task is asyncio.current_task():
                    return
                buffer_flush_task.cancel()
                try:
                    await buffer_flush_task
                except asyncio.CancelledError:
                    pass
                finally:
                    buffer_flush_task = None

            async def flush_buffered_events(*, cancel_timer: bool = False) -> None:
                nonlocal buffered_events, buffer_flush_task
                if not buffered_events:
                    if cancel_timer:
                        await cancel_buffer_flush_task()
                    return
                if cancel_timer:
                    await cancel_buffer_flush_task()
                await persistence_service.append_events(buffered_events)
                buffered_events = []
                if buffer_flush_task is asyncio.current_task():
                    buffer_flush_task = None

            def schedule_buffer_flush() -> None:
                nonlocal buffer_flush_task
                if buffer_flush_task is not None:
                    return

                async def _flush_after_delay() -> None:
                    nonlocal buffer_flush_task
                    try:
                        await asyncio.sleep(self.STREAM_BATCH_MAX_DELAY_SECONDS)
                        await flush_buffered_events()
                    except asyncio.CancelledError:
                        raise
                    finally:
                        if buffer_flush_task is asyncio.current_task():
                            buffer_flush_task = None

                buffer_flush_task = asyncio.create_task(_flush_after_delay())

            async def persist_terminal_success(event: SSEEvent) -> None:
                await flush_buffered_events(cancel_timer=True)
                await persistence_service.persist_terminal_success(event)

            async def persist_terminal_error(event: SSEEvent) -> None:
                await flush_buffered_events(cancel_timer=True)
                await persistence_service.persist_terminal_error(event)

            async def persist_hitl_requested(event: SSEEvent) -> None:
                await flush_buffered_events(cancel_timer=True)
                await persistence_service.persist_hitl_requested(event)

            try:
                if replay_after_event_id:
                    try:
                        for replay_event in await load_replay_events(replay_after_event_id):
                            yield replay_event.to_sse_format(include_id=True)
                    except Exception as exc:
                        logger.warning(
                            "stream replay preload failed; continuing live stream",
                            run_id=str(run.id),
                            after_event_id=replay_after_event_id,
                            error=str(exc),
                        )

                async for event in agent.run(
                    request_id=str(run.id),
                    run_id=run.id,
                    conversation_id=str(conversation_id),
                    user_id=str(user_id),
                    query=run.query,
                    pending_resume_value=pending_resume_value,
                    client_message_id=client_message_id,
                    should_interrupt=lambda: asyncio.sleep(0, result=interrupt_event.is_set()),
                ):
                    if event.event_type in self.STREAM_BATCH_EVENT_TYPES:
                        yield event.to_sse_format(include_id=True)
                        buffered_events.append(event)
                        schedule_buffer_flush()
                        if len(buffered_events) >= self.STREAM_BATCH_SIZE:
                            await flush_buffered_events(cancel_timer=True)
                        continue

                    if event.event_type == "done":
                        await asyncio.shield(persist_terminal_success(event))
                        yield event.to_sse_format(include_id=True)
                        return

                    if event.event_type == "error":
                        await asyncio.shield(persist_terminal_error(event))
                        yield event.to_sse_format(include_id=True)
                        return

                    if event.event_type == "hitl_requested":
                        await asyncio.shield(persist_hitl_requested(event))
                        waiting_for_resume = True
                        yield event.to_sse_format(include_id=True)
                        return

                    await flush_buffered_events(cancel_timer=True)
                    await persistence_service.append_event(event)
                    if pending_resume_value and not resume_input_cleared and event.event_type == "hitl_resolved":
                        await persistence_service.clear_pending_resume()
                        resume_input_cleared = True
                    yield event.to_sse_format(include_id=True)

                await flush_buffered_events(cancel_timer=True)
                if waiting_for_resume:
                    return
            finally:
                await cancel_buffer_flush_task()
                interrupt_event.set()
                interrupt_listener.cancel()
                with suppress(asyncio.CancelledError):
                    await interrupt_listener

        return ChatRunStreamHandle(
            event_stream=event_stream(),
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
