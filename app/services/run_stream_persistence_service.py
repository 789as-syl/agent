"""Persist run status and append-only SSE events for the business shell."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import RunStatus
from app.repositories.run_event_repo import RunEventRepository
from app.schemas.sse_event import ErrorData, SSEEvent
from app.services.chat_run_service import ChatRunService
from app.services.run_event_playback_service import RunEventPlaybackService


class RunStreamPersistenceService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession],
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        self.session_factory = session_factory
        self.run_id = run_id
        self.conversation_id = conversation_id
        self.user_id = user_id

    async def mark_running(self) -> None:
        await self._update_run_status(RunStatus.RUNNING)

    async def mark_success(self) -> None:
        await self._update_run_status(RunStatus.SUCCESS)

    async def mark_failed(self, error_message: str | None = None) -> None:
        await self._update_run_status(RunStatus.FAILED, error_message)

    async def mark_interrupted(self, error_message: str | None = None) -> None:
        await self._update_run_status(RunStatus.INTERRUPTED, error_message)

    async def append_event(self, event: SSEEvent) -> None:
        await self.append_events([event])

    async def append_events(self, events: list[SSEEvent]) -> None:
        if not events:
            return
        async with self.session_factory() as isolated_session:
            playback_service = RunEventPlaybackService(RunEventRepository(isolated_session))
            await playback_service.append_events(
                run_id=self.run_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                events=events,
            )
            await isolated_session.commit()

    async def clear_pending_resume(self) -> None:
        async with self.session_factory() as isolated_session:
            chat_run_service = ChatRunService(isolated_session)
            await chat_run_service.update_run_shell_state(self.run_id, clear_pending_resume=True)
            await isolated_session.commit()

    async def persist_hitl_requested(self, event: SSEEvent) -> None:
        await self.append_event(event)

    async def persist_terminal_success(self, event: SSEEvent) -> None:
        async with self.session_factory() as isolated_session:
            playback_service = RunEventPlaybackService(RunEventRepository(isolated_session))
            isolated_service = ChatRunService(isolated_session)
            await playback_service.append_event(
                run_id=self.run_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                event=event,
            )
            await isolated_service.update_run_status(self.run_id, RunStatus.SUCCESS)
            await isolated_session.commit()

    async def persist_terminal_error(self, event: SSEEvent) -> None:
        error_data = event.trace_data if isinstance(event.trace_data, ErrorData) else ErrorData(
            error_code="STREAM_ERROR",
            error_message="stream returned invalid error payload",
            recoverable=False,
        )
        status = RunStatus.INTERRUPTED if error_data.error_code == "AGENT_INTERRUPTED" else RunStatus.FAILED

        async with self.session_factory() as isolated_session:
            playback_service = RunEventPlaybackService(RunEventRepository(isolated_session))
            isolated_service = ChatRunService(isolated_session)
            await playback_service.append_event(
                run_id=self.run_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                event=event,
            )
            await isolated_service.update_run_status(self.run_id, status, error_data.error_message)
            await isolated_session.commit()

    async def handle_error_event(self, event: SSEEvent) -> None:
        await self.persist_terminal_error(event)

    async def _update_run_status(self, status: RunStatus, error_message: str | None = None) -> None:
        async with self.session_factory() as isolated_session:
            isolated_service = ChatRunService(isolated_session)
            await isolated_service.update_run_status(self.run_id, status, error_message)
            await isolated_session.commit()
