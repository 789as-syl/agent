from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_run import ChatRun
from app.models.conversation import Conversation
from app.models.enums import RunStatus
from app.models.run_event import RunEvent
from app.models.user import User
from app.repositories.run_event_repo import RunEventRepository
from app.schemas.sse_event import ExecutionTraceData, FinalAnswerData, SSEEvent
from app.services.run_event_playback_service import RunEventPlaybackService


async def _create_conversation(db_session: AsyncSession, test_user: User) -> Conversation:
    conversation = Conversation(id=uuid4(), user_id=test_user.id, title="Playback Test", is_deleted=False)
    db_session.add(conversation)
    await db_session.flush()
    return conversation


@pytest.mark.asyncio
async def test_run_event_playback_orders_events_by_step_then_sequence(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = await _create_conversation(db_session, test_user)
    run = ChatRun(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=test_user.id,
        query="hello",
        status=RunStatus.SUCCESS,
        shell_state_json={},
    )
    db_session.add(run)
    await db_session.flush()

    later_event = SSEEvent.create_event(
        event_type="final_answer",
        request_id=str(run.id),
        conversation_id=str(conversation.id),
        step=2,
        trace_data=FinalAnswerData(answer="second", content_blocks=None),
    )
    earlier_event = SSEEvent.create_event(
        event_type="final_answer",
        request_id=str(run.id),
        conversation_id=str(conversation.id),
        step=1,
        trace_data=FinalAnswerData(answer="first", content_blocks=None),
    )

    db_session.add(
        RunEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            user_id=test_user.id,
            event_id=later_event.event_id,
            event_type=later_event.event_type,
            step=later_event.step,
            is_final=False,
            event_json=later_event.model_dump(mode="python"),
        )
    )
    db_session.add(
        RunEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            user_id=test_user.id,
            event_id=earlier_event.event_id,
            event_type=earlier_event.event_type,
            step=earlier_event.step,
            is_final=False,
            event_json=earlier_event.model_dump(mode="python"),
        )
    )
    await db_session.commit()

    playback_service = RunEventPlaybackService(RunEventRepository(db_session))
    events = await playback_service.list_events(run.id)

    assert [event.step for event in events] == [1, 2]
    assert [getattr(event.trace_data, "answer", None) for event in events] == ["first", "second"]


@pytest.mark.asyncio
async def test_run_event_playback_slice_uses_canonical_step_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = await _create_conversation(db_session, test_user)
    run = ChatRun(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=test_user.id,
        query="hello",
        status=RunStatus.SUCCESS,
        shell_state_json={},
    )
    db_session.add(run)
    await db_session.flush()

    second_event = SSEEvent.create_event(
        event_type="final_answer",
        request_id=str(run.id),
        conversation_id=str(conversation.id),
        step=2,
        trace_data=FinalAnswerData(answer="second", content_blocks=None),
    )
    first_event = SSEEvent.create_event(
        event_type="final_answer",
        request_id=str(run.id),
        conversation_id=str(conversation.id),
        step=1,
        trace_data=FinalAnswerData(answer="first", content_blocks=None),
    )

    db_session.add(
        RunEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            user_id=test_user.id,
            event_id=second_event.event_id,
            event_type=second_event.event_type,
            step=second_event.step,
            is_final=False,
            event_json=second_event.model_dump(mode="python"),
        )
    )
    db_session.add(
        RunEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            user_id=test_user.id,
            event_id=first_event.event_id,
            event_type=first_event.event_type,
            step=first_event.step,
            is_final=False,
            event_json=first_event.model_dump(mode="python"),
        )
    )
    await db_session.commit()

    playback_service = RunEventPlaybackService(RunEventRepository(db_session))
    playback = await playback_service.get_slice(run.id, after_event_id=first_event.event_id)

    assert playback.anchor_found is True
    assert [event.step for event in playback.events] == [2]
    assert getattr(playback.events[0].trace_data, "answer", None) == "second"


@pytest.mark.asyncio
async def test_run_event_playback_accepts_legacy_execution_trace_payload(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = await _create_conversation(db_session, test_user)
    run = ChatRun(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=test_user.id,
        query="trace replay",
        status=RunStatus.SUCCESS,
        shell_state_json={},
    )
    db_session.add(run)
    await db_session.flush()

    legacy_event_id = str(uuid4())
    legacy_event_json = {
        "event_id": legacy_event_id,
        "request_id": str(run.id),
        "conversation_id": str(conversation.id),
        "event_type": "execution_trace",
        "step": 1,
        "timestamp": "2026-04-22T00:00:00Z",
        "trace_data": {
            "kind": "tool_result",
                "title": "工具返回：knowledge_retrieval",
            "status": "completed",
            "result_summary": "legacy summary only",
        },
        "is_final": False,
    }

    db_session.add(
        RunEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            user_id=test_user.id,
            event_id=legacy_event_id,
            event_type="execution_trace",
            step=1,
            is_final=False,
            event_json=legacy_event_json,
        )
    )
    await db_session.commit()

    playback_service = RunEventPlaybackService(RunEventRepository(db_session))
    events = await playback_service.list_events(run.id)
    playback = await playback_service.get_slice(run.id)

    assert len(events) == 1
    assert len(playback.events) == 1
    assert isinstance(events[0].trace_data, ExecutionTraceData)
    assert events[0].trace_data.result_summary == "legacy summary only"
