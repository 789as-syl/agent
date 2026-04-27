"""Persisted run-event playback helpers."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.run_event import RunEvent
from app.repositories.run_event_repo import RunEventRepository
from app.schemas.sse_event import SSEEvent


@dataclass(slots=True)
class RunEventPlaybackSlice:
    """Playback-ready slice of persisted run events."""

    events: list[SSEEvent]
    last_event_id: str | None
    after_event_id: str | None = None
    anchor_found: bool = True


class RunEventPlaybackService:
    """Persist and read append-only run-event transcripts."""

    def __init__(self, run_event_repo: RunEventRepository):
        self.run_event_repo = run_event_repo

    async def append_event(
        self,
        *,
        run_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        event: SSEEvent,
    ) -> RunEvent:
        return await self.run_event_repo.create(
            RunEvent(
                run_id=run_id,
                conversation_id=conversation_id,
                user_id=user_id,
                event_id=event.event_id,
                event_type=event.event_type,
                step=event.step,
                is_final=event.is_final,
                event_json=event.model_dump(mode="python"),
            )
        )

    async def append_events(
        self,
        *,
        run_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        events: list[SSEEvent],
    ) -> list[RunEvent]:
        if not events:
            return []
        return await self.run_event_repo.create_many(
            [
                RunEvent(
                    run_id=run_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    step=event.step,
                    is_final=event.is_final,
                    event_json=event.model_dump(mode="python"),
                )
                for event in events
            ]
        )

    async def list_events(self, run_id: UUID) -> list[SSEEvent]:
        rows = await self.run_event_repo.list_by_run_id(run_id)
        return [SSEEvent.model_validate(row.event_json) for row in rows]

    async def get_slice(
        self,
        run_id: UUID,
        *,
        after_event_id: str | None = None,
    ) -> RunEventPlaybackSlice:
        if after_event_id is None:
            events = await self.list_events(run_id)
            return RunEventPlaybackSlice(
                events=events,
                last_event_id=events[-1].event_id if events else None,
            )

        rows, anchor_found = await self.run_event_repo.list_after_event_id(run_id, after_event_id)
        if not anchor_found:
            events = await self.list_events(run_id)
            return RunEventPlaybackSlice(
                events=events,
                last_event_id=events[-1].event_id if events else None,
                after_event_id=after_event_id,
                anchor_found=False,
            )

        events = [SSEEvent.model_validate(row.event_json) for row in rows]
        return RunEventPlaybackSlice(
            events=events,
            last_event_id=events[-1].event_id if events else after_event_id,
            after_event_id=after_event_id,
            anchor_found=True,
        )
