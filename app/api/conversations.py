"""API routes for conversations."""
# ruff: noqa: B008

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime.memory_writeback import sanitize_assistant_answer
from app.api.dependencies import get_current_user
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.engine import get_async_session
from app.models.user import User
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
)
from app.schemas.message import MessageListResponse, MessageResponse
from app.services.conversation_service import ConversationService
from app.tools.result_protocol import sanitize_protocol_mapping

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def _parse_metadata_uuid(metadata: dict[str, Any], field: str) -> UUID | None:
    raw_value = metadata.get(field)
    if not isinstance(raw_value, str):
        return None
    try:
        return UUID(raw_value)
    except ValueError:
        return None


def _normalize_trace_anchor(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    start = value.get("start")
    end = value.get("end")
    if isinstance(start, int) and isinstance(end, int) and start >= 0 and end >= start:
        return {"start": start, "end": end}
    return None


def _normalize_trace_evidence(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        label = item.get("label")
        if not isinstance(source, str) or not source.strip() or not isinstance(label, str) or not label.strip():
            continue
        payload: dict[str, Any] = {"source": source, "label": label}
        detail = item.get("detail")
        if isinstance(detail, str) and detail.strip():
            payload["detail"] = detail
        event_id = item.get("event_id")
        if isinstance(event_id, str) and event_id.strip():
            payload["event_id"] = event_id
        reasoning_range = _normalize_trace_anchor(item.get("reasoning_range"))
        if reasoning_range is not None:
            payload["reasoning_range"] = reasoning_range
        normalized.append(payload)
    return normalized or None


def _tool_input_detail(value: Any) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    for key in ("query", "expression", "prompt"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    try:
        import json

        return json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        return None


def _normalize_execution_trace(execution_trace: Any, *, default_timestamp: int) -> list[dict[str, Any]] | None:
    if not isinstance(execution_trace, list):
        return None
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(execution_trace, start=1):
        if not isinstance(item, dict):
            continue
        metadata_candidate = item.get("metadata")
        metadata = sanitize_protocol_mapping(metadata_candidate) if isinstance(metadata_candidate, dict) else {}
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            title = str(metadata.get("tool_name") or "执行轨迹")
        detail = item.get("detail")
        if not isinstance(detail, str) or not detail.strip():
            legacy_detail = item.get("result_summary")
            if isinstance(legacy_detail, str) and legacy_detail.strip():
                detail = legacy_detail
            else:
                detail = _tool_input_detail(metadata.get("tool_input"))

        entry: dict[str, Any] = {
            "id": str(item.get("id") or f"trace-{index}"),
            "kind": str(item.get("kind") or "execution"),
            "title": title,
            "status": str(item.get("status") or "completed"),
            "timestamp": int(item.get("timestamp") or default_timestamp),
        }
        semantic_key = item.get("semantic_key")
        if isinstance(semantic_key, str) and semantic_key.strip():
            entry["semantic_key"] = semantic_key.strip()
        if detail:
            entry["detail"] = detail
        decision_code = item.get("decision_code")
        if isinstance(decision_code, str) and decision_code.strip():
            entry["decision_code"] = decision_code
        evidence = _normalize_trace_evidence(item.get("evidence"))
        if evidence is not None:
            entry["evidence"] = evidence
        reasoning_anchor = _normalize_trace_anchor(item.get("reasoning_anchor"))
        if reasoning_anchor is not None:
            entry["reasoning_anchor"] = reasoning_anchor
        if metadata:
            entry["metadata"] = metadata
        normalized.append(entry)
    return normalized or None


_PROTOCOL_BLOCK_KEYS = {
    "tool",
    "protocol_version",
    "protocol_path",
    "retrieval_failed",
    "payload",
    "evidence_blocks",
    "error_code",
}


def _is_protocol_content_block(block: Any) -> bool:
    return isinstance(block, dict) and any(key in block for key in _PROTOCOL_BLOCK_KEYS)


def _sanitize_content_blocks(content_blocks: Any) -> list[dict[str, Any]] | None:
    if not isinstance(content_blocks, list):
        return None
    sanitized: list[dict[str, Any]] = []
    for block in content_blocks:
        if not isinstance(block, dict) or _is_protocol_content_block(block):
            continue
        cleaned = sanitize_protocol_mapping(block)
        text = cleaned.get("text")
        if isinstance(text, str):
            cleaned["text"] = sanitize_assistant_answer(text)
            if not cleaned["text"].strip():
                continue
        if cleaned:
            sanitized.append(cleaned)
    return sanitized or None


def _serialize_message(msg: Any) -> MessageResponse:
    metadata = msg.metadata_json or {}
    reply_to_message_id = _parse_metadata_uuid(metadata, "reply_to_message_id")
    execution_trace = _normalize_execution_trace(
        metadata.get("execution_trace"),
        default_timestamp=int(msg.created_at.timestamp() * 1000),
    )
    return MessageResponse(
        id=msg.id,
        conversation_id=msg.conversation_id,
        run_id=_parse_metadata_uuid(metadata, "run_id"),
        role=msg.role,
        content=sanitize_assistant_answer(msg.content) if msg.role == "assistant" else msg.content,
        content_blocks=_sanitize_content_blocks(msg.content_blocks_json),
        execution_trace=execution_trace,
        created_at=msg.created_at,
        reply_to_message_id=reply_to_message_id,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ConversationListResponse:
    service = ConversationService(session)
    items, total = await service.list_conversations(user_id=current_user.id, skip=skip, limit=limit)
    return ConversationListResponse(items=[ConversationResponse.model_validate(item) for item in items], total=total)


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ConversationResponse:
    service = ConversationService(session)
    conversation = await service.create_conversation(user_id=current_user.id, title=request.title)
    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ConversationResponse:
    service = ConversationService(session)
    conversation = await service.get_conversation(user_id=current_user.id, conversation_id=conversation_id)
    return ConversationResponse.model_validate(conversation)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    request: ConversationUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ConversationResponse:
    service = ConversationService(session)
    updated = await service.update_title(
        user_id=current_user.id,
        conversation_id=conversation_id,
        new_title=request.title,
    )
    return ConversationResponse.model_validate(updated)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    service = ConversationService(session)
    await service.delete_conversation(user_id=current_user.id, conversation_id=conversation_id)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> MessageListResponse:
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.get_by_user_and_id(current_user.id, conversation_id)
    if not conversation:
        existing = await conv_repo.get_by_id(conversation_id)
        if existing and existing.user_id != current_user.id:
            raise PermissionDeniedError(message="您无权访问此会话")
        raise NotFoundError(error_code="CONVERSATION_NOT_FOUND", message="会话不存在")

    msg_repo = MessageRepository(session)
    messages, total = await msg_repo.list_by_conversation(conversation_id=conversation_id, skip=skip, limit=limit)
    return MessageListResponse(
        items=[_serialize_message(msg) for msg in messages],
        total=total,
        skip=skip,
        limit=limit,
    )
