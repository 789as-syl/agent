"""Chat run creation, streaming, HITL resume, and playback endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import create_native_agent
from app.agents.runtime.constants import REQUEST_HUMAN_INPUT_TOOL_NAME
from app.api.dependencies import get_current_user
from app.core.redis import (
    CHAT_RUN_INTERRUPT_SIGNAL_TTL_SECONDS,
    build_chat_run_interrupt_channel,
    build_chat_run_interrupt_flag_key,
    redis_client,
)
from app.models.chat_run import ChatRun
from app.models.engine import get_async_session, get_async_session_factory
from app.models.enums import RunStatus
from app.models.user import User
from app.repositories.run_event_repo import RunEventRepository
from app.schemas.sse_event import SSEEvent
from app.services.chat_run_service import ChatRunService
from app.services.chat_run_stream_service import ChatRunStreamService
from app.services.run_event_playback_service import RunEventPlaybackService
from app.services.run_resume_service import RunResumeService, RunResumeSnapshot

router = APIRouter(prefix="/conversations", tags=["Chat Runs"])


class ChatRunCreateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=200)


class ChatRunAssociationRequest(BaseModel):
    client_message_id: str | None = Field(default=None, min_length=1, max_length=200)


class ChatRunCreateResponse(BaseModel):
    run_id: str
    status: str


class ChatRunMutationResponse(BaseModel):
    status: str
    run_id: str
    message: str | None = None


class HITLDecisionPayload(BaseModel):
    type: Literal["respond", "approve", "edit", "reject"]
    value: str | dict[str, Any] | None = None


class ChatRunResumeRequest(BaseModel):
    decision: HITLDecisionPayload


class ChatRunRuntimeState(BaseModel):
    hitl: dict[str, Any] | None = None
    client_message_id: str | None = None


class ChatRunStatusResponse(BaseModel):
    run_id: str
    status: str
    query: str
    error_message: str | None = None
    runtime_state: ChatRunRuntimeState


class RunEventPlaybackResponse(BaseModel):
    after_event_id: str | None = None
    anchor_found: bool = True
    last_event_id: str | None = None
    events: list[SSEEvent] = Field(default_factory=list)


def _status_value(status_value: RunStatus | str) -> str:
    return status_value.value if isinstance(status_value, RunStatus) else str(status_value)


async def _build_runtime_state(run: ChatRun) -> ChatRunRuntimeState:
    payload = await RunResumeService().build_runtime_state_payload(run)
    return ChatRunRuntimeState.model_validate(payload)


@router.post(
    "/{conversation_id}/runs",
    response_model=ChatRunCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_run(
    conversation_id: uuid.UUID,
    request: ChatRunCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ChatRunCreateResponse:
    run_service = ChatRunService(session)
    run = await run_service.create_run(
        conversation_id=conversation_id,
        user_id=current_user.id,
        query=request.query,
        client_message_id=request.client_message_id,
    )
    return ChatRunCreateResponse(
        run_id=str(run.id),
        status=_status_value(run.status),
    )


@router.get(
    "/{conversation_id}/runs/{run_id}",
    response_model=ChatRunStatusResponse,
)
async def get_chat_run(
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ChatRunStatusResponse:
    run_service = ChatRunService(session)
    try:
        run = await run_service.get_run_for_conversation(run_id, current_user.id, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat run not found") from exc

    return ChatRunStatusResponse(
        run_id=str(run.id),
        status=_status_value(run.status),
        query=run.query,
        error_message=run.error_message,
        runtime_state=await _build_runtime_state(run),
    )


@router.get(
    "/{conversation_id}/runs/{run_id}/events",
    response_model=RunEventPlaybackResponse,
)
async def get_chat_run_events(
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    after_event_id: str | None = Query(default=None),
) -> RunEventPlaybackResponse:
    run_service = ChatRunService(session)
    try:
        run = await run_service.get_run_for_conversation(run_id, current_user.id, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat run not found") from exc

    playback_service = RunEventPlaybackService(RunEventRepository(session))
    playback_slice = await playback_service.get_slice(run.id, after_event_id=after_event_id)
    return RunEventPlaybackResponse(
        after_event_id=playback_slice.after_event_id,
        anchor_found=playback_slice.anchor_found,
        last_event_id=playback_slice.last_event_id,
        events=playback_slice.events,
    )


@router.get(
    "/{conversation_id}/runs/{run_id}/stream",
    response_class=StreamingResponse,
)
async def stream_chat_run(
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    after_event_id: str | None = Query(default=None),
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
) -> Response:
    session_factory = get_async_session_factory()
    run_service = ChatRunService(session)
    try:
        run = await run_service.get_run_for_conversation(run_id, current_user.id, conversation_id)
        await run_service.ensure_run_is_active_owner(run=run, requested_action="stream")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat run not found") from exc

    try:
        ChatRunStreamService.validate_run_for_stream(run)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"run already completed", "run interrupted; create a retry run"}:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    stream_service = ChatRunStreamService(
        session=session,
        session_factory=session_factory,
        agent_factory=create_native_agent,
    )
    stream_handle = await stream_service.prepare_stream(
        run=run,
        conversation_id=conversation_id,
        user_id=current_user.id,
        replay_after_event_id=after_event_id or last_event_id_header,
    )
    return StreamingResponse(
        stream_handle.event_stream,
        media_type="text/event-stream",
        headers=stream_handle.headers,
    )


@router.post(
    "/{conversation_id}/runs/{run_id}/interrupt",
    response_model=ChatRunMutationResponse,
)
async def interrupt_chat_run(
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ChatRunMutationResponse:
    run_service = ChatRunService(session)
    try:
        await run_service.get_run_for_conversation(run_id, current_user.id, conversation_id)
        await run_service.interrupt_run(run_id, current_user.id)
        await session.commit()
        await redis_client.setex(
            build_chat_run_interrupt_flag_key(run_id),
            CHAT_RUN_INTERRUPT_SIGNAL_TTL_SECONDS,
            "1",
        )
        await redis_client.publish(build_chat_run_interrupt_channel(run_id), "interrupt")
        return ChatRunMutationResponse(
            status="interrupted",
            run_id=str(run_id),
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat run not found") from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


@router.post(
    "/{conversation_id}/runs/{run_id}/retry",
    response_model=ChatRunMutationResponse,
)
async def retry_chat_run(
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    request: ChatRunAssociationRequest | None = None,
) -> ChatRunMutationResponse:
    run_service = ChatRunService(session)
    try:
        await run_service.get_run_for_conversation(run_id, current_user.id, conversation_id)
        run = await run_service.retry_run(
            run_id,
            current_user.id,
            client_message_id=request.client_message_id if request else None,
        )
        return ChatRunMutationResponse(
            status=_status_value(run.status),
            run_id=str(run.id),
            message="created a new retry run",
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat run not found") from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


@router.post(
    "/{conversation_id}/runs/{run_id}/resume",
    response_model=ChatRunMutationResponse,
)
async def resume_chat_run(
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    request: ChatRunResumeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ChatRunMutationResponse:
    run_service = ChatRunService(session)
    resume_service = RunResumeService()
    try:
        run = await run_service.get_run_for_conversation(run_id, current_user.id, conversation_id)
        await run_service.ensure_run_is_active_owner(run=run, requested_action="resume")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat run not found") from exc

    snapshot = await resume_service.build_resume_snapshot(run)
    runtime_state = ChatRunRuntimeState.model_validate(
        await resume_service.build_runtime_state_payload(run)
    )
    if not snapshot.resume_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=snapshot.reason or "resume not supported",
        )
    if not bool((runtime_state.hitl or {}).get("pending")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="run is not waiting for human input")

    normalized = _normalize_hitl_decision(snapshot=snapshot, decision=request.decision)
    await run_service.queue_resume_input(run.id, response=normalized)
    await session.commit()

    return ChatRunMutationResponse(
        status=_status_value(run.status),
        run_id=str(run.id),
        message="human decision accepted",
    )


@router.post(
    "/{conversation_id}/runs/{run_id}/regenerate",
    response_model=ChatRunMutationResponse,
)
async def regenerate_chat_run(
    conversation_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    request: ChatRunAssociationRequest | None = None,
) -> ChatRunMutationResponse:
    run_service = ChatRunService(session)
    try:
        await run_service.get_run_for_conversation(run_id, current_user.id, conversation_id)
        run = await run_service.regenerate_run(
            run_id,
            current_user.id,
            client_message_id=request.client_message_id if request else None,
        )
        return ChatRunMutationResponse(
            status=_status_value(run.status),
            run_id=str(run.id),
            message="created a new regenerate run",
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chat run not found") from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


def _normalize_hitl_decision(*, snapshot: RunResumeSnapshot, decision: HITLDecisionPayload) -> dict[str, Any]:
    allowed = set(snapshot.allowed_actions)
    if decision.type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decision is not allowed for current HITL state",
        )

    if decision.type == "reject":
        message = str(decision.value or "User rejected the action")
        return {
            "decision_type": "reject",
            "decision": {"type": "reject", "message": message},
            "decisions": [{"type": "reject", "message": message}],
        }

    if decision.type == "approve":
        return {
            "decision_type": "approve",
            "decision": {"type": "approve"},
            "decisions": [{"type": "approve"}],
        }

    if snapshot.action_name == REQUEST_HUMAN_INPUT_TOOL_NAME and decision.type == "respond":
        response_text = str(decision.value or "")
        edited_action: dict[str, Any] = {
            "name": REQUEST_HUMAN_INPUT_TOOL_NAME,
            "args": {
                **snapshot.action_args,
                "response": response_text,
            },
        }
        return {
            "decision_type": "respond",
            "decision": {"type": "edit", "edited_action": edited_action},
            "decisions": [{"type": "edit", "edited_action": edited_action}],
        }

    if decision.type == "edit" and isinstance(decision.value, dict):
        return {
            "decision_type": "edit",
            "decision": {"type": "edit", "edited_action": decision.value},
            "decisions": [{"type": "edit", "edited_action": decision.value}],
        }

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid HITL decision payload")
