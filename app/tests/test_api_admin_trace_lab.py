from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_run import ChatRun
from app.models.conversation import Conversation
from app.models.enums import RunStatus
from app.models.run_event import RunEvent
from app.models.user import User
from app.schemas.sse_event import ExecutionTraceData, SSEEvent


@pytest.mark.asyncio
async def test_admin_trace_lab_lists_runs_and_redacts_events(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = Conversation(id=uuid4(), user_id=test_user.id, title="Trace Lab", is_deleted=False)
    run = ChatRun(
        id=uuid4(),
        conversation_id=conversation.id,
        user_id=test_user.id,
        query="trace me",
        status=RunStatus.SUCCESS,
        shell_state_json={},
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(run)
    await db_session.flush()
    event = SSEEvent.create_event(
        event_type="execution_trace",
        request_id=str(run.id),
        conversation_id=str(conversation.id),
        step=1,
        trace_data=ExecutionTraceData(
            kind="tool_result",
            title="工具完成",
            detail="safe detail",
            status="completed",
            metadata={"provider_payload": {"secret": True}, "safe_count": 1},
        ),
    )
    db_session.add(
        RunEvent(
            run_id=run.id,
            conversation_id=conversation.id,
            user_id=test_user.id,
            event_id=event.event_id,
            event_type=event.event_type,
            step=event.step,
            is_final=False,
            event_json=event.model_dump(mode="python"),
        )
    )
    await db_session.commit()

    user_response = await client.get("/api/v1/admin/trace-runs", headers=auth_headers)
    assert user_response.status_code == 403

    list_response = await client.get("/api/v1/admin/trace-runs", headers=admin_auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1

    detail_response = await client.get(f"/api/v1/admin/trace-runs/{run.id}", headers=admin_auth_headers)
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["events"][0]["title"] == "工具完成"
    assert payload["events"][0]["metadata"]["provider_payload"] == "[redacted internal trace payload]"
    assert "secret" not in str(payload)
