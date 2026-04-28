"""Thin business-shell runner over the native-only create_agent runtime."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.langgraph_native_runtime import build_native_runtime
from app.agents.middleware.defaults import NativeAgentContext
from app.agents.runtime.constants import REQUEST_HUMAN_INPUT_TOOL_NAME
from app.agents.runtime.memory_writeback import sanitize_assistant_answer
from app.agents.runtime.native_checkpoint import (
    build_runtime_config,
    get_checkpoint_messages,
    get_pending_interrupt,
)
from app.agents.runtime.native_model import message_content_to_blocks, message_content_to_text
from app.core.langsmith import build_langsmith_metadata, langsmith_enabled
from app.core.log_config import get_logger
from app.schemas.sse_event import (
    AnswerBasis,
    DoneData,
    ErrorData,
    ExecutionTraceData,
    FinalAnswerData,
    GenerationDeltaData,
    HITLRequestedData,
    HITLResolvedData,
    ReasoningDeltaData,
    SSEEvent,
    TraceEvidence,
    TraceRange,
)
from app.services.conversation_memory_service import ConversationMemoryService
from app.tools.result_protocol import format_tool_result_for_model, parse_tool_result_payload, sanitize_protocol_mapping

logger = get_logger(__name__)


class NativeAgentInterruptedError(RuntimeError):
    """Raised when the native runner is interrupted by outer business logic."""


@dataclass(slots=True)
class TraceAnchor:
    start: int
    end: int


@dataclass(slots=True)
class TraceEvidenceItem:
    source: str
    label: str
    detail: str | None = None
    event_id: str | None = None
    reasoning_range: TraceAnchor | None = None
    title: str | None = None
    snippet: str | None = None
    source_type: str | None = None
    locator: str | None = None
    evidence_type: str | None = None


@dataclass(slots=True)
class CanonicalTrace:
    kind: str
    title: str
    status: str
    detail: str | None = None
    decision_code: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    result_count: int | None = None
    retrieval_failed: bool | None = None
    answer_basis: AnswerBasis | None = None
    evidence: list[TraceEvidenceItem] = field(default_factory=list)
    reasoning_anchor: TraceAnchor | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    semantic_key: str | None = None


class NativeAgentRunner:
    """Run the native agent and adapt stream outputs to the business SSE contract."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.memory_service = ConversationMemoryService(db_session)
        self._compiled_agent: Any | None = None

    async def _ensure_agent(self) -> Any:
        if self._compiled_agent is None:
            self._compiled_agent = await build_native_runtime(self.db_session)
        return self._compiled_agent

    async def _bootstrap_seed_messages(
        self,
        *,
        conversation_id: uuid.UUID,
        query: str,
    ) -> tuple[list[BaseMessage], str | None]:
        messages: list[BaseMessage] = []
        short_memory = await self.memory_service.load_short_memory(conversation_id)
        summary_text, _ = await self.memory_service.load_long_memory_summary(conversation_id)
        for msg in short_memory:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                content = msg.content_blocks_json or msg.content
                messages.append(AIMessage(content=cast(str | list[str | dict[str, Any]], content)))
        if (
            not messages
            or not isinstance(messages[-1], HumanMessage)
            or message_content_to_text(messages[-1].content) != query
        ):
            messages.append(HumanMessage(content=query))
        return messages, summary_text

    async def run(
        self,
        *,
        request_id: str,
        run_id: uuid.UUID,
        conversation_id: str,
        user_id: str,
        query: str,
        pending_resume_value: dict[str, Any] | None = None,
        client_message_id: str | None = None,
        should_interrupt: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        start_time = time.time()
        step = 0
        accumulated_answer = ""
        raw_answer_accumulated = ""
        final_answer = ""
        final_content_blocks: list[dict[str, Any]] | None = None
        execution_trace: list[dict[str, Any]] = []
        emitted_trace_keys: set[str] = set()
        memory_summary: str | None = None
        query_intent: dict[str, Any] | None = None
        if pending_resume_value is None:
            query_intent = _classify_query_intent(query)
            if bool(query_intent["short_circuit"]):
                guidance = str(query_intent["message"])
                short_circuit_trace = _build_short_circuit_trace(query_intent)
                step += 1
                yield SSEEvent.create_event(
                    event_type="execution_trace",
                    request_id=request_id,
                    conversation_id=conversation_id,
                    step=step,
                    trace_data=_canonical_trace_to_sse_data(short_circuit_trace),
                )
                execution_trace.append(_canonical_trace_to_entry(short_circuit_trace, step=step))
                final_answer = guidance
                final_content_blocks = [{"type": "text", "text": guidance}]
                step += 1
                yield SSEEvent.create_event(
                    event_type="final_answer",
                    request_id=request_id,
                    conversation_id=conversation_id,
                    step=step,
                    trace_data=FinalAnswerData(
                        answer=final_answer,
                        content_blocks=final_content_blocks,
                    ),
                )
                await self._persist_after_run(
                    conversation_id=uuid.UUID(conversation_id),
                    query=query,
                    run_id=run_id,
                    final_answer=final_answer,
                    final_content_blocks=final_content_blocks,
                    execution_trace=execution_trace,
                    reasoning_redacted=False,
                    client_message_id=client_message_id,
                )
                step += 1
                yield SSEEvent.create_event(
                    event_type="done",
                    request_id=request_id,
                    conversation_id=conversation_id,
                    step=step,
                    trace_data=DoneData(
                        total_steps=step,
                        duration_ms=int((time.time() - start_time) * 1000),
                        success=True,
                    ),
                    is_final=True,
                )
                return

        agent = await self._ensure_agent()
        thread_id = conversation_id
        config = build_runtime_config(thread_id=thread_id)
        if langsmith_enabled():
            config["metadata"] = build_langsmith_metadata(
                conversation_id=conversation_id,
                run_id=str(run_id),
            )
        hitl_pending = False
        reasoning_accumulated = ""
        reasoning_persisted_chars = 0
        reasoning_buffer = ""
        reasoning_source: str | None = None
        reasoning_last_emit_at = 0.0
        reasoning_truncated = False
        existing_messages = await get_checkpoint_messages(thread_id=thread_id)
        interrupt_payload = await get_pending_interrupt(thread_id=thread_id) if pending_resume_value else None

        if pending_resume_value is None:
            if existing_messages:
                stream_input: dict[str, Any] | Command = {"messages": [HumanMessage(content=query)]}
                memory_summary, _ = await self.memory_service.load_long_memory_summary(uuid.UUID(conversation_id))
                seen_message_count = len(existing_messages)
            else:
                initial_messages, memory_summary = await self._bootstrap_seed_messages(
                    conversation_id=uuid.UUID(conversation_id),
                    query=query,
                )
                stream_input = {"messages": initial_messages}
                seen_message_count = len(initial_messages)
        else:
            memory_summary, _ = await self.memory_service.load_long_memory_summary(uuid.UUID(conversation_id))
            stream_input = Command(resume=pending_resume_value)
            seen_message_count = len(existing_messages)
            step += 1
            yield SSEEvent.create_event(
                event_type="hitl_resolved",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=HITLResolvedData(
                    kind=_hitl_kind(interrupt_payload),
                ),
            )

        context = NativeAgentContext(
            request_id=request_id,
            conversation_id=conversation_id,
            user_id=user_id,
            memory_summary=memory_summary,
        )
        # Intent classification is an internal routing concern.  Do not emit
        # user-visible scope/matched-signal traces for ordinary chat runs.

        try:
            direct_answer_trace_emitted = False
            tool_call_observed = False
            async for chunk in agent.astream(
                stream_input,
                config=config,
                context=context,
                stream_mode=["values", "messages"],
            ):
                if should_interrupt and await should_interrupt():
                    raise NativeAgentInterruptedError("run interrupted")

                if isinstance(chunk, tuple):
                    mode, payload = chunk
                    if mode == "messages":
                        message, _metadata = payload
                        direct_answer_trace = None
                        if (
                            isinstance(message, AIMessageChunk)
                            and message_content_to_text(getattr(message, "content", None))
                            and not getattr(message, "tool_call_chunks", None)
                            and not direct_answer_trace_emitted
                            and not tool_call_observed
                        ):
                            direct_answer_trace = _build_direct_answer_trace(
                                query_intent=query_intent,
                                reasoning_accumulated=reasoning_accumulated,
                            )
                        if direct_answer_trace is not None:
                            emitted, step = _emit_trace_event(
                                trace=direct_answer_trace,
                                request_id=request_id,
                                conversation_id=conversation_id,
                                step=step,
                                execution_trace=execution_trace,
                                emitted_trace_keys=emitted_trace_keys,
                            )
                            if emitted is not None:
                                yield emitted
                            direct_answer_trace_emitted = True
                        reasoning_chunk: tuple[str, int, str, str | None, float, bool, SSEEvent | None] = (
                            _ingest_reasoning_chunk(
                            message=message,
                            accumulated=reasoning_accumulated,
                            persisted_chars=reasoning_persisted_chars,
                            buffered_delta=reasoning_buffer,
                            source=reasoning_source,
                            last_emit_at=reasoning_last_emit_at,
                            step=step,
                            request_id=request_id,
                            conversation_id=conversation_id,
                            truncated=reasoning_truncated,
                            )
                        )
                        reasoning_delta_event: SSEEvent | None
                        (
                            reasoning_accumulated,
                            reasoning_persisted_chars,
                            reasoning_buffer,
                            reasoning_source,
                            reasoning_last_emit_at,
                            reasoning_truncated,
                            reasoning_delta_event,
                        ) = reasoning_chunk
                        if reasoning_delta_event is not None:
                            step += 1
                            yield reasoning_delta_event.model_copy(update={"step": step})
                        delta = _compute_generation_delta(message=message, accumulated=raw_answer_accumulated)
                        if delta:
                            raw_candidate_answer = raw_answer_accumulated + delta
                            candidate_answer = sanitize_assistant_answer(raw_candidate_answer)
                            raw_answer_accumulated = raw_candidate_answer
                            if not candidate_answer and _looks_like_pending_tool_protocol(raw_candidate_answer):
                                continue
                            safe_delta = _compute_generation_delta_from_text(
                                text=candidate_answer,
                                accumulated=accumulated_answer,
                            )
                            if safe_delta:
                                accumulated_answer = candidate_answer
                                step += 1
                                yield SSEEvent.create_event(
                                    event_type="generation_delta",
                                    request_id=request_id,
                                    conversation_id=conversation_id,
                                    step=step,
                                    trace_data=GenerationDeltaData(
                                        delta=safe_delta,
                                    ),
                                )
                    continue

                values = chunk
                if not isinstance(values, dict):
                    continue

                if "__interrupt__" in values:
                    interrupt_value = _extract_interrupt_payload(values["__interrupt__"])
                    clarification_trace = _build_clarification_trace(
                        interrupt_value=interrupt_value,
                        reasoning_accumulated=reasoning_accumulated,
                    )
                    emitted, step = _emit_trace_event(
                        trace=clarification_trace,
                        request_id=request_id,
                        conversation_id=conversation_id,
                        step=step,
                        execution_trace=execution_trace,
                        emitted_trace_keys=emitted_trace_keys,
                    )
                    if emitted is not None:
                        yield emitted
                    step += 1
                    yield SSEEvent.create_event(
                        event_type="hitl_requested",
                        request_id=request_id,
                        conversation_id=conversation_id,
                        step=step,
                        trace_data=HITLRequestedData(
                            kind=_hitl_kind(interrupt_value),
                            prompt=_hitl_prompt(interrupt_value),
                            allowed_actions=_hitl_allowed_actions(interrupt_value),
                        ),
                    )
                    hitl_pending = True
                    break

                messages = values.get("messages")
                if not isinstance(messages, list):
                    continue

                new_messages = messages[seen_message_count:]
                for message in new_messages:
                    if isinstance(message, AIMessage) and message.tool_calls:
                        for tool_call in message.tool_calls:
                            tool_name = str(tool_call.get("name") or "unknown")
                            if tool_name == REQUEST_HUMAN_INPUT_TOOL_NAME:
                                continue
                            tool_call_observed = True
                            tool_trace = _build_tool_call_trace(
                                tool_name=tool_name,
                                tool_input=tool_call.get("args", {}),
                                query_intent=query_intent,
                                reasoning_accumulated=reasoning_accumulated,
                            )
                            emitted, step = _emit_trace_event(
                                trace=tool_trace,
                                request_id=request_id,
                                conversation_id=conversation_id,
                                step=step,
                                execution_trace=execution_trace,
                                emitted_trace_keys=emitted_trace_keys,
                            )
                            if emitted is not None:
                                yield emitted
                    elif isinstance(message, ToolMessage):
                        if message.name == REQUEST_HUMAN_INPUT_TOOL_NAME:
                            continue
                        parsed = parse_tool_result_payload(message.artifact or message.content) or {}
                        result_trace = _build_tool_result_trace(
                            tool_name=message.name or str(parsed.get("tool") or "unknown"),
                            parsed=parsed,
                            raw_content=message.content,
                        )
                        emitted, step = _emit_trace_event(
                            trace=result_trace,
                            request_id=request_id,
                            conversation_id=conversation_id,
                            step=step,
                            execution_trace=execution_trace,
                            emitted_trace_keys=emitted_trace_keys,
                        )
                        if emitted is not None:
                            yield emitted
                    elif isinstance(message, AIMessage) and not message.tool_calls:
                        final_answer = message_content_to_text(message.content)
                        final_content_blocks = message_content_to_blocks(message.content)

                seen_message_count = len(messages)

            if hitl_pending:
                return

            if reasoning_buffer:
                while reasoning_buffer:
                    step += 1
                    delta = reasoning_buffer[:REASONING_MAX_EVENT_CHARS]
                    reasoning_buffer = reasoning_buffer[REASONING_MAX_EVENT_CHARS:]
                    if reasoning_truncated and not reasoning_buffer:
                        delta = f"{delta}\n[... reasoning truncated ...]"
                    yield SSEEvent.create_event(
                        event_type="reasoning_delta",
                        request_id=request_id,
                        conversation_id=conversation_id,
                        step=step,
                        trace_data=ReasoningDeltaData(
                            delta=delta,
                            source=reasoning_source,
                            truncated=reasoning_truncated,
                        ),
                    )
                reasoning_buffer = ""

            latest_messages = await get_checkpoint_messages(thread_id=thread_id)
            latest_assistant_message = _find_last_assistant_message(latest_messages)
            if latest_assistant_message is not None:
                if not final_answer:
                    final_answer = message_content_to_text(latest_assistant_message.content)
                if final_content_blocks is None:
                    final_content_blocks = message_content_to_blocks(latest_assistant_message.content)
            if not final_answer and accumulated_answer:
                final_answer = accumulated_answer
            final_answer = sanitize_assistant_answer(final_answer)
            final_content_blocks = _sanitize_final_content_blocks(final_content_blocks, final_answer)
            accumulated_answer = sanitize_assistant_answer(accumulated_answer)
            if not accumulated_answer:
                accumulated_answer = final_answer
            step += 1
            yield SSEEvent.create_event(
                event_type="final_answer",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=FinalAnswerData(
                    answer=final_answer,
                    content_blocks=final_content_blocks,
                ),
            )
            await self._persist_after_run(
                conversation_id=uuid.UUID(conversation_id),
                query=query,
                run_id=run_id,
                final_answer=final_answer,
                final_content_blocks=final_content_blocks,
                execution_trace=execution_trace,
                reasoning_redacted=bool(reasoning_accumulated),
                client_message_id=client_message_id,
            )
            step += 1
            yield SSEEvent.create_event(
                event_type="done",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=DoneData(
                    total_steps=step,
                    duration_ms=int((time.time() - start_time) * 1000),
                    success=True,
                ),
                is_final=True,
            )
        except NativeAgentInterruptedError as exc:
            step += 1
            yield SSEEvent.create_event(
                event_type="error",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=ErrorData(
                    error_code="AGENT_INTERRUPTED",
                    error_message=str(exc),
                    recoverable=True,
                ),
                is_final=True,
            )
        except Exception as exc:
            step += 1
            yield SSEEvent.create_event(
                event_type="error",
                request_id=request_id,
                conversation_id=conversation_id,
                step=step,
                trace_data=ErrorData(
                    error_code="NATIVE_RUNTIME_ERROR",
                    error_message=str(exc),
                    recoverable=False,
                ),
                is_final=True,
            )

    async def _persist_after_run(
        self,
        *,
        conversation_id: uuid.UUID,
        query: str,
        run_id: uuid.UUID,
        final_answer: str,
        final_content_blocks: list[dict[str, Any]] | None,
        execution_trace: list[dict[str, Any]] | None,
        reasoning_redacted: bool,
        client_message_id: str | None = None,
    ) -> None:
        await self.memory_service.persist_run_messages(
            conversation_id=conversation_id,
            query=query,
            final_answer=final_answer,
            final_content_blocks=final_content_blocks,
            execution_trace=execution_trace,
            reasoning_redacted=reasoning_redacted,
            run_id=run_id,
            client_message_id=client_message_id,
        )
        # The streaming endpoint persists run events using an isolated session.
        # Commit message rows here before the later `done` event is marked
        # successful, otherwise the client may refetch after completion and see
        # an empty conversation even though the stream already finished.
        await self.db_session.commit()
        try:
            await self.memory_service.maybe_update_summary(conversation_id)
            await self.db_session.commit()
        except Exception as exc:  # pragma: no cover - defensive optional-memory guard
            await self.db_session.rollback()
            logger.warning(
                "conversation summary update skipped after message persistence",
                conversation_id=str(conversation_id),
                run_id=str(run_id),
                error=str(exc),
            )


def create_native_agent(db_session: AsyncSession) -> NativeAgentRunner:
    return NativeAgentRunner(db_session)


def _find_last_assistant_message(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return message
    return None


def _compute_generation_delta(*, message: BaseMessage, accumulated: str) -> str:
    text = message_content_to_text(getattr(message, "content", None))
    if not text:
        return ""
    if isinstance(message, AIMessageChunk):
        return text
    return _compute_generation_delta_from_text(text=text, accumulated=accumulated)


def _compute_generation_delta_from_text(*, text: str, accumulated: str) -> str:
    if accumulated and text.startswith(accumulated):
        return text[len(accumulated):]
    return text if not accumulated else ""


def _looks_like_pending_tool_protocol(text: str) -> bool:
    stripped = str(text or "").lstrip()
    if not stripped.startswith("{"):
        return False
    markers = (
        '"success"',
        '"tool"',
        '"protocol_version"',
        '"protocol_path"',
        '"retrieval_failed"',
        '"payload"',
        'knowledge_retrieval',
    )
    return any(marker in stripped for marker in markers)


def _sanitize_final_content_blocks(
    content_blocks: list[dict[str, Any]] | None,
    final_answer: str,
) -> list[dict[str, Any]] | None:
    if not content_blocks:
        return None
    sanitized_blocks = [
        block
        for block in content_blocks
        if isinstance(block, dict) and not _is_tool_protocol_block(block)
    ]
    if sanitized_blocks:
        return sanitized_blocks
    return [{"type": "text", "text": final_answer}] if final_answer else None


def _is_tool_protocol_block(block: dict[str, Any]) -> bool:
    return any(
        key in block
        for key in (
            "tool",
            "protocol_version",
            "protocol_path",
            "retrieval_failed",
            "payload",
            "evidence_blocks",
            "error_code",
        )
    )


def _extract_interrupt_payload(payload: Any) -> dict[str, Any]:
    interrupt = payload[0] if isinstance(payload, (tuple, list)) and payload else payload
    interrupt_value = getattr(interrupt, "value", interrupt)
    return dict(interrupt_value) if isinstance(interrupt_value, dict) else {}


def _hitl_prompt(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "请提供下一步所需的人类输入。"
    action_requests = payload.get("action_requests")
    if isinstance(action_requests, list) and action_requests:
        first = action_requests[0] or {}
        if isinstance(first, dict):
            return str(
                first.get("description")
                or (first.get("args") or {}).get("prompt")
                or "请提供下一步所需的人类输入。"
            )
    return "请提供下一步所需的人类输入。"


def _hitl_kind(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "input"
    action_requests = payload.get("action_requests")
    if isinstance(action_requests, list) and action_requests:
        first = action_requests[0] or {}
        if isinstance(first, dict):
            args = first.get("args") or {}
            if isinstance(args, dict):
                return str(args.get("kind") or "input")
    return "input"


def _hitl_allowed_actions(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    review_configs = payload.get("review_configs")
    if isinstance(review_configs, list) and review_configs:
        first = review_configs[0] or {}
        if isinstance(first, dict):
            raw = [str(item) for item in (first.get("allowed_decisions") or [])]
            return ["respond" if item == "edit" else item for item in raw]
    return []


def _canonical_trace_to_sse_data(trace: CanonicalTrace) -> ExecutionTraceData:
    semantic_key = _trace_semantic_key(trace)
    return ExecutionTraceData(
        kind=trace.kind,
        title=trace.title,
        detail=trace.detail,
        status=trace.status,
        decision_code=_trace_visible_decision_code(trace),
        tool_name=trace.tool_name,
        tool_input=trace.tool_input,
        result_count=trace.result_count,
        retrieval_failed=None,
        answer_basis=trace.answer_basis,
        semantic_key=semantic_key,
        evidence=[_trace_evidence_model(item) for item in trace.evidence] or None,
        reasoning_anchor=_trace_anchor_model(trace.reasoning_anchor),
        metadata=_safe_trace_metadata(trace.metadata) or None,
    )


def _canonical_trace_to_entry(trace: CanonicalTrace, *, step: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"trace-{step}",
        "kind": trace.kind,
        "title": trace.title,
        "status": trace.status,
        "timestamp": int(time.time() * 1000),
        "semantic_key": _trace_semantic_key(trace),
    }
    if trace.detail:
        payload["detail"] = trace.detail
    visible_decision_code = _trace_visible_decision_code(trace)
    if visible_decision_code:
        payload["decision_code"] = visible_decision_code
    if trace.answer_basis:
        payload["answer_basis"] = trace.answer_basis
    if trace.evidence:
        payload["evidence"] = [_trace_evidence_payload(item) for item in trace.evidence]
    if trace.reasoning_anchor is not None:
        payload["reasoning_anchor"] = _trace_anchor_payload(trace.reasoning_anchor)

    merged_metadata = _safe_trace_metadata(trace.metadata)
    if trace.tool_name is not None:
        merged_metadata["tool_name"] = trace.tool_name
    if trace.tool_input is not None:
        merged_metadata["tool_input"] = trace.tool_input
    if trace.result_count is not None:
        merged_metadata["result_count"] = trace.result_count
    # retrieval_failed is an internal protocol flag; status/title already carry the user-facing state.
    if merged_metadata:
        payload["metadata"] = merged_metadata
    return payload


def _trace_semantic_key(trace: CanonicalTrace) -> str:
    if trace.semantic_key:
        return trace.semantic_key
    parts = [trace.kind, _trace_visible_decision_code(trace) or "", trace.tool_name or ""]
    if trace.kind == "tool_call" and trace.tool_input:
        parts.append(_stable_hash(trace.tool_input))
    elif trace.kind == "tool_result":
        parts.append(str(trace.result_count if trace.result_count is not None else ""))
        parts.append(str(trace.status or ""))
    else:
        parts.append(trace.title)
    return ":".join(part for part in parts if part)


def _stable_hash(value: Any) -> str:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        payload = str(value)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _trace_visible_decision_code(trace: CanonicalTrace) -> str | None:
    if trace.decision_code == "retrieval_failed" and trace.answer_basis == "retrieval_unavailable":
        return "retrieval_unavailable"
    return trace.decision_code


def _safe_trace_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return sanitize_protocol_mapping(dict(metadata or {}))


def _emit_trace_event(
    *,
    trace: CanonicalTrace,
    request_id: str,
    conversation_id: str,
    step: int,
    execution_trace: list[dict[str, Any]],
    emitted_trace_keys: set[str],
) -> tuple[SSEEvent | None, int]:
    semantic_key = _trace_semantic_key(trace)
    if semantic_key in emitted_trace_keys:
        return None, step
    emitted_trace_keys.add(semantic_key)
    next_step = step + 1
    event = SSEEvent.create_event(
        event_type="execution_trace",
        request_id=request_id,
        conversation_id=conversation_id,
        step=next_step,
        trace_data=_canonical_trace_to_sse_data(trace),
    )
    execution_trace.append(_canonical_trace_to_entry(trace, step=next_step))
    return event, next_step


def _trace_anchor_payload(anchor: TraceAnchor | None) -> dict[str, int] | None:
    if anchor is None:
        return None
    return {"start": anchor.start, "end": anchor.end}


def _trace_anchor_model(anchor: TraceAnchor | None) -> TraceRange | None:
    if anchor is None:
        return None
    return TraceRange(start=anchor.start, end=anchor.end)


def _trace_evidence_payload(item: TraceEvidenceItem) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": item.source,
        "label": item.label,
    }
    if item.detail:
        payload["detail"] = item.detail
    if item.event_id:
        payload["event_id"] = item.event_id
    if item.reasoning_range is not None:
        payload["reasoning_range"] = _trace_anchor_payload(item.reasoning_range)
    if item.title:
        payload["title"] = item.title
    if item.snippet:
        payload["snippet"] = item.snippet
    if item.source_type:
        payload["source_type"] = item.source_type
    if item.locator:
        payload["locator"] = item.locator
    if item.evidence_type:
        payload["evidence_type"] = item.evidence_type
    return payload


def _trace_evidence_model(item: TraceEvidenceItem) -> TraceEvidence:
    return TraceEvidence(
        source=item.source,
        label=item.label,
        detail=item.detail,
        event_id=item.event_id,
        reasoning_range=_trace_anchor_model(item.reasoning_range),
        title=item.title,
        snippet=item.snippet,
        source_type=item.source_type,
        locator=item.locator,
        evidence_type=item.evidence_type,
    )


def _build_short_circuit_trace(query_intent: dict[str, Any]) -> CanonicalTrace:
    reason = str(query_intent.get("reason") or "out_of_scope")
    title = "判定为闲聊问题" if reason == "casual_chat" else "判定为创新创业域外问题"
    detail_parts = []
    signal_detail = _query_signal_detail(query_intent)
    if signal_detail:
        detail_parts.append(f"命中信号：{signal_detail}")
    detail_parts.append(
        "当前问题不进入创新创业知识问答主链，系统已直接返回引导说明。"
        if reason == "casual_chat"
        else "当前问题未命中创新创业/资料/计算范围，系统已直接返回引导说明。"
    )
    return CanonicalTrace(
        kind="scope_check",
        title=title,
        status="completed",
        detail="\n".join(detail_parts),
        decision_code=f"short_circuit_{reason}",
        evidence=_classifier_evidence(query_intent),
        metadata={"strategy": "short-circuit", "reason": reason},
    )


def _build_direct_answer_trace(
    *,
    query_intent: dict[str, Any] | None,
    reasoning_accumulated: str,
) -> CanonicalTrace | None:
    return CanonicalTrace(
        kind="decision",
        title="直接回答",
        status="completed",
        detail="本轮未调用外部工具，基于模型已有上下文生成回答。",
        decision_code="direct_answer",
        answer_basis="direct",
        semantic_key="decision:direct_answer",
    )


def _build_clarification_trace(
    *,
    interrupt_value: dict[str, Any],
    reasoning_accumulated: str,
) -> CanonicalTrace:
    _ = reasoning_accumulated
    prompt = _hitl_prompt(interrupt_value)
    evidence = [TraceEvidenceItem(source="interrupt", label="触发人工澄清", detail=prompt)]
    return CanonicalTrace(
        kind="clarification",
        title=f"请求澄清：{_summarize_prompt(prompt)}",
        status="completed",
        detail=prompt,
        decision_code="clarify_missing_context",
        answer_basis="needs_clarification",
        evidence=evidence,
        reasoning_anchor=None,
        metadata={"strategy": "clarify"},
    )


def _build_tool_call_trace(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    query_intent: dict[str, Any] | None,
    reasoning_accumulated: str,
) -> CanonicalTrace:
    _ = reasoning_accumulated
    title = _tool_call_title(tool_name=tool_name, query_intent=query_intent)
    evidence: list[TraceEvidenceItem] = []
    evidence.append(
        TraceEvidenceItem(
            source="tool_call",
            label=f"工具请求：{tool_name}",
            detail=_tool_input_preview(tool_input),
        )
    )
    detail_parts = []
    input_preview = _tool_input_preview(tool_input)
    if input_preview:
        detail_parts.append(f"工具输入：{input_preview}")
    return CanonicalTrace(
        kind="tool_call",
        title=title,
        status="running",
        detail="\n".join(detail_parts) if detail_parts else None,
        decision_code=f"tool_call_{tool_name}",
        tool_name=tool_name,
        tool_input=tool_input,
        evidence=evidence,
        reasoning_anchor=None,
    )


def _build_tool_result_trace(
    *,
    tool_name: str,
    parsed: dict[str, Any],
    raw_content: Any,
) -> CanonicalTrace:
    success = bool(parsed.get("success", not parsed.get("retrieval_failed", False)))
    result_count = _safe_int(parsed.get("result_count", parsed.get("total_count")))
    retrieval_failed = bool(parsed.get("retrieval_failed", False))
    status = "completed" if success or retrieval_failed else "error"
    title = _tool_result_title(
        tool_name=tool_name,
        success=success,
        result_count=result_count,
        retrieval_failed=retrieval_failed,
        parsed=parsed,
    )
    detail = _tool_result_detail(tool_name=tool_name, parsed=parsed, raw_content=raw_content)
    evidence = _tool_result_evidence(
        tool_name=tool_name,
        result_count=result_count,
        retrieval_failed=retrieval_failed,
        parsed=parsed,
    )
    return CanonicalTrace(
        kind="tool_result",
        title=title,
        status=status,
        detail=detail,
        decision_code=_tool_result_decision_code(
            tool_name=tool_name,
            success=success,
            result_count=result_count,
            retrieval_failed=retrieval_failed,
        ),
        tool_name=tool_name,
        result_count=result_count,
        retrieval_failed=retrieval_failed,
        answer_basis=_tool_result_answer_basis(
            tool_name=tool_name,
            success=success,
            result_count=result_count,
            retrieval_failed=retrieval_failed,
        ),
        evidence=evidence,
        metadata=_tool_result_metadata(
            tool_name=tool_name,
            parsed=parsed,
            retrieval_failed=retrieval_failed,
        ),
    )


def _tool_result_metadata(
    *,
    tool_name: str,
    parsed: dict[str, Any],
    retrieval_failed: bool,
) -> dict[str, Any]:
    if tool_name == "knowledge_retrieval":
        metadata: dict[str, Any] = {}
        if retrieval_failed:
            metadata["fallback"] = "direct_generation"
        return metadata
    safe: dict[str, Any] = {}
    if "result" in parsed and tool_name == "math_calculator":
        safe["result"] = parsed.get("result")
    return safe


def _ingest_reasoning_chunk(
    *,
    message: BaseMessage,
    accumulated: str,
    persisted_chars: int,
    buffered_delta: str,
    source: str | None,
    last_emit_at: float,
    step: int,
    request_id: str,
    conversation_id: str,
    truncated: bool,
) -> tuple[str, int, str, str | None, float, bool, SSEEvent | None]:
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    raw_delta = str(additional_kwargs.get("reasoning_delta") or "")
    raw_accumulated = str(additional_kwargs.get("reasoning_accumulated") or accumulated)
    raw_source = str(additional_kwargs.get("reasoning_source") or source or "") or None
    if not raw_delta or truncated:
        return accumulated, persisted_chars, buffered_delta, raw_source, last_emit_at, truncated, None

    remaining_budget = max(REASONING_MAX_PERSISTED_CHARS - persisted_chars, 0)
    if remaining_budget <= 0:
        return accumulated, persisted_chars, buffered_delta, raw_source, last_emit_at, True, None

    delta = raw_delta[:remaining_budget]
    next_truncated = truncated or len(raw_delta) > remaining_budget
    next_accumulated = (
        raw_accumulated
        if raw_accumulated and raw_accumulated.startswith(accumulated)
        else accumulated + delta
    )
    next_buffer = buffered_delta + delta
    next_persisted = persisted_chars + len(delta)
    now = time.time()

    should_emit = (
        (now - last_emit_at) >= REASONING_MIN_EMIT_INTERVAL_SECONDS
        or getattr(message, "chunk_position", None) == "last"
    )
    if not should_emit or not next_buffer:
        return next_accumulated, next_persisted, next_buffer, raw_source, last_emit_at, next_truncated, None

    event_delta = next_buffer[:REASONING_MAX_EVENT_CHARS]
    overflow = next_buffer[REASONING_MAX_EVENT_CHARS:]
    if next_truncated and not overflow:
        event_delta = f"{event_delta}\n[... reasoning truncated ...]"
    event = SSEEvent.create_event(
        event_type="reasoning_delta",
        request_id=request_id,
        conversation_id=conversation_id,
        step=step + 1,
        trace_data=ReasoningDeltaData(
            delta=event_delta,
            source=raw_source,
            truncated=next_truncated,
        ),
    )
    return next_accumulated, next_persisted, overflow, raw_source, now, next_truncated, event


def _query_signal_detail(query_intent: dict[str, Any] | None) -> str | None:
    matched_signals = _matched_signal_list(query_intent)
    if not matched_signals:
        return None
    return "、".join(matched_signals[:4])


def _classifier_evidence(query_intent: dict[str, Any] | None) -> list[TraceEvidenceItem]:
    matched_signals = _matched_signal_list(query_intent)
    if not matched_signals:
        return []
    return [
        TraceEvidenceItem(
            source="classifier",
            label="命中问题信号",
            detail="、".join(matched_signals[:4]),
        )
    ]


def _matched_signal_list(query_intent: dict[str, Any] | None) -> list[str]:
    if not isinstance(query_intent, dict):
        return []
    return [str(item) for item in query_intent.get("matched_signals", []) if str(item).strip()]


def _summarize_prompt(prompt: str, *, max_chars: int = 24) -> str:
    text = " ".join(str(prompt or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1]}…"


def _tool_input_preview(tool_input: dict[str, Any] | None) -> str | None:
    if not isinstance(tool_input, dict) or not tool_input:
        return None
    for key in ("query", "expression", "prompt"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    compact_items = ", ".join(f"{key}={value}" for key, value in list(tool_input.items())[:3])
    return compact_items or None


def _tool_call_title(*, tool_name: str, query_intent: dict[str, Any] | None) -> str:
    signal_detail = _query_signal_detail(query_intent)
    if tool_name == "knowledge_retrieval":
        if signal_detail:
            return "调用知识库检索：问题需要资料/上下文证据"
        return "调用知识库检索：为回答补充领域证据"
    if tool_name == "web_search":
        return "调用外部搜索：需要最新或外部信息"
    if tool_name == "math_calculator":
        return "调用数值计算：检测到确定性计算请求"
    return f"调用工具：{tool_name}"


def _tool_result_title(
    *,
    tool_name: str,
    success: bool,
    result_count: int | None,
    retrieval_failed: bool,
    parsed: dict[str, Any],
) -> str:
    if tool_name == "knowledge_retrieval":
        if retrieval_failed or not success:
            return "知识库检索暂不可用"
        if result_count and result_count > 0:
            return f"已检索到 {result_count} 条知识库证据"
        return "知识库证据不足"
    if tool_name == "web_search":
        if not success:
            return "外部搜索失败"
        if result_count and result_count > 0:
            return f"外部搜索返回 {result_count} 条结果"
        return "外部搜索未返回结果"
    if tool_name == "math_calculator":
        return "完成数值计算" if success else "数值计算失败"
    message = str(parsed.get("message") or "").strip()
    if message:
        return f"工具返回：{tool_name}"
    return f"工具执行完成：{tool_name}" if success else f"工具执行失败：{tool_name}"


def _tool_result_detail(*, tool_name: str, parsed: dict[str, Any], raw_content: Any) -> str | None:
    detail_parts: list[str] = []
    message = str(parsed.get("message") or "").strip()
    if message:
        detail_parts.append(message)

    if tool_name == "knowledge_retrieval":
        retrieval_failed = bool(parsed.get("retrieval_failed", False))
        result_count = _safe_int(parsed.get("result_count", parsed.get("total_count")))
        if retrieval_failed or not bool(parsed.get("success", not retrieval_failed)):
            if not detail_parts:
                detail_parts.append("知识库检索本轮不可用，回答已回退为非知识库证据模式。")
        elif result_count and result_count > 0:
            evidence_blocks = parsed.get("evidence_blocks")
            if isinstance(evidence_blocks, list) and evidence_blocks:
                titles = [
                    str(item.get("title") or item.get("knowledge_point_id") or "").strip()
                    for item in evidence_blocks
                    if isinstance(item, dict)
                ]
                titles = [item for item in titles if item]
                if titles:
                    detail_parts.append(f"已使用知识库证据：{'；'.join(titles[:3])}")
        else:
            detail_parts.append("已尝试检索知识库，但当前没有足够证据支撑完整回答。")
    elif tool_name == "web_search":
        results = parsed.get("results")
        if isinstance(results, list) and results:
            titles = [str(item.get("title") or "").strip() for item in results if isinstance(item, dict)]
            titles = [item for item in titles if item]
            if titles:
                detail_parts.append(f"返回结果：{'；'.join(titles[:3])}")
    elif tool_name == "math_calculator":
        if "result" in parsed:
            detail_parts.append(f"计算结果：{parsed.get('result')}")

    if not detail_parts and raw_content:
        safe_summary = format_tool_result_for_model(raw_content, tool_name=tool_name)
        if safe_summary:
            detail_parts.append(safe_summary)
    return "\n".join(detail_parts) if detail_parts else None


def _tool_result_decision_code(
    *,
    tool_name: str,
    success: bool,
    result_count: int | None,
    retrieval_failed: bool,
) -> str:
    if tool_name == "knowledge_retrieval":
        if retrieval_failed or not success:
            return "retrieval_unavailable"
        return "retrieval_hit" if result_count and result_count > 0 else "retrieval_insufficient"
    if tool_name == "web_search":
        if not success:
            return "web_search_failed"
        return "web_search_hit" if result_count and result_count > 0 else "web_search_empty"
    if tool_name == "math_calculator":
        return "math_completed" if success else "math_failed"
    return f"{tool_name}_completed" if success else f"{tool_name}_failed"


def _tool_result_answer_basis(
    *,
    tool_name: str,
    success: bool,
    result_count: int | None,
    retrieval_failed: bool,
) -> AnswerBasis | None:
    if tool_name != "knowledge_retrieval":
        return None
    if retrieval_failed or not success:
        return "retrieval_unavailable"
    if result_count and result_count > 0:
        return "knowledge_backed"
    return "evidence_insufficient"


def _tool_result_evidence(
    *,
    tool_name: str,
    result_count: int | None,
    retrieval_failed: bool,
    parsed: dict[str, Any],
) -> list[TraceEvidenceItem]:
    evidence: list[TraceEvidenceItem] = []
    if tool_name == "knowledge_retrieval":
        if retrieval_failed:
            evidence.append(
                TraceEvidenceItem(
                    source="tool_result",
                    label="知识库检索暂不可用",
                    detail="本轮无法提供知识库证据，回答已回退为非知识库证据模式。",
                    title="知识库检索暂不可用",
                    snippet="本轮无法提供知识库证据，回答已回退为非知识库证据模式。",
                    source_type="system",
                    evidence_type="retrieval_status",
                )
            )
            return evidence
        if result_count is not None and result_count <= 0:
            evidence.append(
                TraceEvidenceItem(
                    source="tool_result",
                    label="知识库证据不足",
                    detail="已尝试检索知识库，但当前没有足够证据支撑完整回答。",
                    title="知识库证据不足",
                    snippet="已尝试检索知识库，但当前没有足够证据支撑完整回答。",
                    source_type="system",
                    evidence_type="retrieval_status",
                )
            )
            return evidence
        evidence_blocks = parsed.get("evidence_blocks")
        if isinstance(evidence_blocks, list):
            for item in evidence_blocks[:3]:
                if not isinstance(item, dict):
                    continue
                title = _compact_display_text(
                    item.get("title") or item.get("knowledge_point_id"),
                    max_chars=80,
                )
                if not title:
                    continue
                provenance = item.get("provenance")
                evidence_type = _evidence_type(item.get("group_type"))
                source_type = _evidence_source_type(
                    provenance=provenance,
                    fallback_group_type=evidence_type,
                )
                locator = _evidence_locator(provenance, evidence_type=evidence_type)
                snippet = _build_user_visible_evidence_snippet(
                    item.get("content") or item.get("snippet") or item.get("text"),
                    source_type=source_type,
                    evidence_type=evidence_type,
                )
                detail = _legacy_evidence_detail(locator=locator, snippet=snippet)
                evidence.append(
                    TraceEvidenceItem(
                        source="knowledge_retrieval",
                        label=title,
                        detail=detail,
                        title=title,
                        snippet=snippet,
                        source_type=source_type,
                        locator=locator,
                        evidence_type=evidence_type,
                    )
                )
    if tool_name == "math_calculator" and "result" in parsed:
        evidence.append(
            TraceEvidenceItem(
                source="tool_result",
                label="计算结果",
                detail=str(parsed.get("result")),
            )
        )
    return evidence


EVIDENCE_SNIPPET_MAX_CHARS = 180
EVIDENCE_LOCATOR_MAX_CHARS = 48


def _compact_display_text(value: Any, *, max_chars: int) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1]}…"


def _compact_evidence_snippet(value: Any) -> str | None:
    return _compact_display_text(value, max_chars=EVIDENCE_SNIPPET_MAX_CHARS)


def _build_user_visible_evidence_snippet(
    value: Any,
    *,
    source_type: str | None,
    evidence_type: str | None,
) -> str | None:
    raw_text = str(value or "").strip()
    if not raw_text:
        return None
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if source_type == "question_bank" or evidence_type == "question":
        for prefix in ("题目：", "题干："):
            line = next((item for item in lines if item.startswith(prefix)), None)
            if line:
                return _compact_evidence_snippet(line)
        first_line = lines[0] if lines else raw_text
        return _compact_evidence_snippet(first_line)
    filtered_lines = [
        line
        for line in lines
        if not line.startswith("答案：") and not line.startswith("解析：")
    ]
    text = " ".join(filtered_lines) if filtered_lines else raw_text
    return _compact_evidence_snippet(text)


def _evidence_source_type(*, provenance: Any, fallback_group_type: Any) -> str | None:
    if isinstance(provenance, list):
        for entry in provenance:
            if not isinstance(entry, dict):
                continue
            source_type = _compact_display_text(entry.get("source_type"), max_chars=40)
            if source_type:
                return source_type
    group_type = _compact_display_text(fallback_group_type, max_chars=40)
    if group_type == "question":
        return "question_bank"
    return "document"


def _evidence_type(value: Any) -> str | None:
    return _compact_display_text(value or "section", max_chars=40)


def _evidence_locator(provenance: Any, *, evidence_type: str | None) -> str | None:
    if evidence_type == "question":
        return "题库题目"
    if not isinstance(provenance, list):
        return None
    locators: list[str] = []
    for entry in provenance:
        if not isinstance(entry, dict):
            continue
        page = entry.get("page_number")
        slide = entry.get("slide_number")
        table = entry.get("table_index") or entry.get("table_number")
        chunk = entry.get("chunk_index")
        section_heading = entry.get("section_heading") or entry.get("heading") or entry.get("section_title")
        if page:
            locators.append(f"第 {page} 页")
        elif slide:
            locators.append(f"第 {slide} 页幻灯片")
        elif table:
            locators.append(f"表 {table}")
        elif section_heading:
            locators.append(str(section_heading).strip())
        elif chunk:
            locators.append(f"片段 {chunk}")
        if len(locators) >= 2:
            break
    return _compact_display_text(" / ".join(locators), max_chars=EVIDENCE_LOCATOR_MAX_CHARS)


def _legacy_evidence_detail(*, locator: str | None, snippet: str | None) -> str | None:
    if locator and snippet:
        return _compact_display_text(f"{locator} · {snippet}", max_chars=200)
    return locator or snippet


REASONING_MAX_EVENT_CHARS = 400
REASONING_EVENTS_PER_SECOND = 8
REASONING_MIN_EMIT_INTERVAL_SECONDS = 1 / REASONING_EVENTS_PER_SECOND
REASONING_MAX_PERSISTED_CHARS = 12_000

CASUAL_CHAT_KEYWORDS: tuple[str, ...] = (
    "你好",
    "您好",
    "嗨",
    "hello",
    "hi",
    "在吗",
    "早上好",
    "晚上好",
    "谢谢",
    "再见",
    "讲个笑话",
    "聊天",
    "闲聊",
    "陪我",
    "天气",
    "吃什么",
    "电影",
    "音乐",
    "游戏",
    "星座",
)
DOMAIN_KEYWORDS: tuple[str, ...] = (
    "创新",
    "创业",
    "创业项目",
    "创业机会",
    "商业模式",
    "商业画布",
    "商业计划",
    "商业计划书",
    "价值主张",
    "市场",
    "用户访谈",
    "需求验证",
    "客户",
    "竞品",
    "产品",
    "mvp",
    "增长",
    "融资",
    "路演",
    "投资",
    "估值",
    "团队",
    "创业大赛",
    "startup",
    "entrepreneur",
    "business model",
    "fundraising",
    "pitch",
    "product-market fit",
)
CONTEXT_KEYWORDS: tuple[str, ...] = (
    "知识库",
    "题库",
    "课程",
    "课件",
    "课上",
    "这门课",
    "老师",
    "讲义",
    "资料",
    "文档",
    "文件",
    "上传",
    "项目",
    "代码",
    "agent",
    "逻辑",
    "app",
    "计划书",
    "案例",
    "笔记",
    "日志",
    "报错",
)
MATH_KEYWORDS: tuple[str, ...] = (
    "计算",
    "算一下",
    "公式",
    "比例",
    "增长率",
    "利润率",
    "毛利率",
    "回本",
    "预算",
    "roi",
    "npv",
    "irr",
)
MATH_EXPRESSION_RE = re.compile(r"^[\d\s\+\-\*\/\(\)\.\%\^=]+$")


FACT_LOOKUP_MARKERS: tuple[str, ...] = (
    "在哪",
    "哪里",
    "地址",
    "位置",
    "怎么走",
    "导航",
    "路线",
    "电话",
    "官网",
    "开放时间",
    "几点",
    "什么时候",
    "谁是",
)
STRONG_DOMAIN_MARKERS: tuple[str, ...] = (
    "商业模式",
    "商业画布",
    "商业计划书",
    "价值主张",
    "mvp",
    "融资",
    "路演",
    "pitch",
    "product-market fit",
    "business model",
)
DOMAIN_ACTION_MARKERS: tuple[str, ...] = (
    "分析",
    "设计",
    "梳理",
    "评估",
    "怎么做",
    "如何写",
    "计划书",
    "项目",
    "案例",
)
BROAD_DOMAIN_MARKERS: tuple[str, ...] = (
    "创新",
    "创业",
    "市场",
    "客户",
    "产品",
    "团队",
)


def _classify_query_intent(query: str) -> dict[str, Any]:
    normalized = _normalize_query(query)
    if not normalized:
        return {
            "short_circuit": True,
            "reason": "out_of_scope",
            "message": _out_of_scope_guidance(),
            "matched_signals": [],
        }

    if _is_explicit_math_query(normalized):
        return {
            "short_circuit": False,
            "reason": "math",
            "intent": "math",
            "message": "",
            "matched_signals": [],
        }

    fact_matches = _matched_keywords(normalized, FACT_LOOKUP_MARKERS)
    strong_domain_matches = _matched_keywords(normalized, STRONG_DOMAIN_MARKERS)
    action_matches = _matched_keywords(normalized, DOMAIN_ACTION_MARKERS)
    broad_matches = _matched_keywords(normalized, BROAD_DOMAIN_MARKERS)
    context_matches = _matched_keywords(normalized, CONTEXT_KEYWORDS)
    casual_matches = _matched_keywords(normalized, CASUAL_CHAT_KEYWORDS)

    if fact_matches and not strong_domain_matches:
        location_lookup = any(item in normalized for item in ("在哪", "哪里", "地址", "位置", "导航", "路线"))
        return {
            "short_circuit": False,
            "reason": "fact_lookup",
            "intent": "location_lookup" if location_lookup else "fact_lookup",
            "message": "",
            "matched_signals": [],
        }

    if strong_domain_matches:
        needs_analysis = any(item in normalized for item in ("分析", "评估", "梳理", "设计"))
        intent = "business_analysis" if needs_analysis else "domain_qa"
        return {
            "short_circuit": False,
            "reason": "domain",
            "intent": intent,
            "message": "",
            "matched_signals": strong_domain_matches,
        }

    if broad_matches and action_matches:
        return {
            "short_circuit": False,
            "reason": "domain",
            "intent": "business_analysis",
            "message": "",
            "matched_signals": [*broad_matches, *action_matches],
        }

    if context_matches and not fact_matches:
        return {
            "short_circuit": False,
            "reason": "domain",
            "intent": "domain_qa",
            "message": "",
            "matched_signals": context_matches,
        }

    if casual_matches:
        return {
            "short_circuit": True,
            "reason": "casual_chat",
            "intent": "casual_or_out_of_scope",
            "message": _casual_chat_guidance(),
            "matched_signals": [],
        }
    return {
        "short_circuit": False,
        "reason": "fact_lookup",
        "intent": "fact_lookup",
        "message": "",
        "matched_signals": [],
    }


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return bool(_matched_keywords(text, keywords))


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for keyword in keywords:
        if _is_ascii_keyword(keyword):
            pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
            if re.search(pattern, text):
                matches.append(keyword)
            continue
        if keyword in text:
            matches.append(keyword)
    return matches


def _is_ascii_keyword(keyword: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789 -")
    lowered = keyword.lower()
    return bool(lowered) and all(char in allowed for char in lowered)


def _is_explicit_math_query(text: str) -> bool:
    if _contains_any(text, MATH_KEYWORDS):
        return True
    return _looks_like_math_expression(text)


def _looks_like_math_expression(text: str) -> bool:
    compact = text.replace(" ", "")
    has_digit = any(char.isdigit() for char in compact)
    return has_digit and bool(MATH_EXPRESSION_RE.fullmatch(compact))


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _casual_chat_guidance() -> str:
    return (
        "我是创新创业知识问答助手，目前不提供闲聊服务。"
        "你可以直接提问创业、商业模式、市场验证、融资、团队、课程资料或项目材料相关问题。"
    )


def _out_of_scope_guidance() -> str:
    return (
        "我主要处理创新创业相关问题，并可结合知识库、课程资料和项目材料提供依据。"
        "请改问商业模式、用户访谈、市场分析、融资、团队协作或相关确定性计算问题。"
    )
