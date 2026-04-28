from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agents.native_agent_runner import (
    CanonicalTrace,
    NativeAgentRunner,
    TraceAnchor,
    TraceEvidenceItem,
    _build_direct_answer_trace,
    _build_tool_result_trace,
    _canonical_trace_to_entry,
    _canonical_trace_to_sse_data,
    _compute_generation_delta_from_text,
)
from app.agents.runtime.memory_writeback import sanitize_assistant_answer


class _FakeAgent:
    async def astream(self, *_args, **_kwargs) -> AsyncGenerator[object, None]:
        yield (
            "messages",
            (
                AIMessageChunk(
                    content="",
                    additional_kwargs={
                        "reasoning_delta": "分",
                        "reasoning_accumulated": "分",
                        "reasoning_source": "reasoning_content",
                    },
                ),
                {},
            ),
        )
        yield (
            "messages",
            (
                AIMessageChunk(
                    content="答",
                    chunk_position="last",
                    additional_kwargs={
                        "reasoning_delta": "析",
                        "reasoning_accumulated": "分析",
                        "reasoning_source": "reasoning_content",
                    },
                ),
                {},
            ),
        )
        yield {
            "messages": [
                HumanMessage(content="什么是商业模式画布"),
                AIMessage(content="答案"),
            ]
        }


@pytest.mark.asyncio
async def test_native_agent_runner_emits_reasoning_delta_and_runtime_grounded_trace() -> None:
    db_session = MagicMock()
    runner = NativeAgentRunner(db_session)

    with (
        patch.object(runner.memory_service, "load_short_memory", AsyncMock(return_value=[])),
        patch.object(runner.memory_service, "load_long_memory_summary", AsyncMock(return_value=(None, None))),
        patch.object(runner, "_persist_after_run", AsyncMock()),
        patch("app.agents.native_agent_runner.build_native_runtime", AsyncMock(return_value=_FakeAgent())),
        patch("app.agents.native_agent_runner.get_checkpoint_messages", AsyncMock(return_value=[])),
        patch("app.agents.native_agent_runner.get_pending_interrupt", AsyncMock(return_value=None)),
        patch("app.agents.native_agent_runner.langsmith_enabled", return_value=False),
    ):
        events = [
            event
            async for event in runner.run(
                request_id="req-1",
                run_id=uuid4(),
                conversation_id=str(uuid4()),
                user_id=str(uuid4()),
                query="什么是商业模式画布",
            )
        ]

    event_types = [event.event_type for event in events]
    assert "reasoning_delta" in event_types
    assert "generation_delta" in event_types
    assert "final_answer" in event_types
    assert "done" in event_types
    generation_events = [event for event in events if event.event_type == "generation_delta"]
    reasoning_events = [event for event in events if event.event_type == "reasoning_delta"]
    assert generation_events
    assert reasoning_events
    assert all(getattr(event.trace_data, "accumulated", None) is None for event in generation_events)
    assert all(getattr(event.trace_data, "accumulated", None) is None for event in reasoning_events)
    execution_trace_events = [
        event
        for event in events
        if event.event_type == "execution_trace"
    ]
    reasoning_titles = [getattr(event.trace_data, "title", "") for event in execution_trace_events]
    assert "开始直接回答" not in reasoning_titles
    decision_codes = [getattr(event.trace_data, "decision_code", None) for event in execution_trace_events]
    assert "scope_domain" not in decision_codes
    assert decision_codes.count("direct_answer") == 1
    direct_trace = next(
        event
        for event in execution_trace_events
        if getattr(event.trace_data, "decision_code", None) == "direct_answer"
    )
    assert getattr(direct_trace.trace_data, "title", "") == "直接回答"
    assert "reasoning" not in (getattr(direct_trace.trace_data, "detail", "") or "").lower()


@pytest.mark.asyncio
async def test_native_agent_runner_short_circuits_casual_chat_without_loading_agent() -> None:
    db_session = MagicMock()
    runner = NativeAgentRunner(db_session)

    with (
        patch.object(runner, "_persist_after_run", AsyncMock()) as persist_mock,
        patch(
            "app.agents.native_agent_runner.build_native_runtime",
            AsyncMock(side_effect=AssertionError("agent should not load")),
        ),
    ):
        events = [
            event
            async for event in runner.run(
                request_id="req-2",
                run_id=uuid4(),
                conversation_id=str(uuid4()),
                user_id=str(uuid4()),
                query="你好呀，陪我聊聊天",
            )
        ]

    assert [event.event_type for event in events] == ["execution_trace", "final_answer", "done"]
    assert getattr(events[0].trace_data, "decision_code", "") == "short_circuit_casual_chat"
    assert "不提供闲聊服务" in getattr(events[1].trace_data, "answer", "")
    persist_mock.assert_awaited_once()


def test_trace_adapters_preserve_field_level_parity() -> None:
    trace = CanonicalTrace(
        kind="tool_result",
        title="知识库命中 2 条证据",
        status="completed",
        detail="命中证据：商业模式画布；MVP",
        decision_code="retrieval_hit",
        tool_name="knowledge_retrieval",
        tool_input={"query": "商业模式画布"},
        result_count=2,
        retrieval_failed=False,
        evidence=[
            TraceEvidenceItem(source="classifier", label="命中问题信号", detail="商业模式"),
        ],
        reasoning_anchor=TraceAnchor(start=3, end=8),
        metadata={"payload": {"tool": "knowledge_retrieval"}},
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=3)

    assert streamed.kind == persisted["kind"]
    assert streamed.title == persisted["title"]
    assert streamed.status == persisted["status"]
    assert streamed.detail == persisted["detail"]
    assert streamed.tool_name == persisted["metadata"]["tool_name"]
    assert streamed.tool_input == persisted["metadata"]["tool_input"]
    assert streamed.result_count == persisted["metadata"]["result_count"]
    assert streamed.retrieval_failed is None
    assert "retrieval_failed" not in persisted["metadata"]
    assert streamed.semantic_key == persisted["semantic_key"]
    assert streamed.decision_code == persisted["decision_code"]


def test_knowledge_retrieval_failure_trace_uses_safe_fallback_metadata() -> None:
    trace = _build_tool_result_trace(
        tool_name="knowledge_retrieval",
        parsed={
            "success": False,
            "tool": "knowledge_retrieval",
            "message": "知识库检索暂不可用，已切换为直接回答",
            "result_count": 0,
            "retrieval_failed": True,
            "error_code": "RETRIEVAL_PROVIDER_UNAVAILABLE",
            "error": "DashScope embedding request failed: ConnectionResetError(10054)",
        },
        raw_content="raw tool json should not be shown",
    )

    assert trace.status == "completed"
    assert trace.title in {"知识库检索暂不可用", "知识库检索失败"}
    assert trace.detail == "知识库检索暂不可用，已切换为直接回答"
    assert trace.decision_code == "retrieval_unavailable"
    assert trace.retrieval_failed is True
    assert trace.metadata == {
        "fallback": "direct_generation",
    }
    assert "DashScope" not in (trace.detail or "")
    assert "payload" not in trace.metadata


def test_generation_delta_sanitizer_removes_tool_json_prefix_before_streaming() -> None:
    raw_text = (
        '{"success": false, "tool": "knowledge_retrieval", '
        '"message": "知识库检索暂不可用，已切换为直接回答", '
        '"payload": {"error_code": "RETRIEVAL_PROVIDER_UNAVAILABLE"}}'
        '商业模式画布是用于梳理商业模式的工具。'
    )
    sanitized = sanitize_assistant_answer(raw_text)
    delta = _compute_generation_delta_from_text(text=sanitized, accumulated="")

    assert delta == "商业模式画布是用于梳理商业模式的工具。"
    assert "knowledge_retrieval" not in delta
    assert "RETRIEVAL_PROVIDER_UNAVAILABLE" not in delta


def test_partial_tool_protocol_prefix_is_suppressed_until_natural_answer_arrives() -> None:
    partial = '{"success": false, "tool": "knowledge_retrieval", "payload": {'
    sanitized_partial = sanitize_assistant_answer(partial)
    assert sanitized_partial == ""

    full = (
        '{"success": false, "tool": "knowledge_retrieval", '
        '"payload": {"error_code": "RETRIEVAL_PROVIDER_UNAVAILABLE"}}'
        '商业模式画布是用于梳理商业模式的工具。'
    )
    sanitized_full = sanitize_assistant_answer(full)
    delta = _compute_generation_delta_from_text(text=sanitized_full, accumulated="")

    assert delta == "商业模式画布是用于梳理商业模式的工具。"
    assert "payload" not in delta
    assert "knowledge_retrieval" not in delta


def test_direct_answer_trace_is_visible_but_not_internal_reasoning() -> None:
    trace = _build_direct_answer_trace(query_intent=None, reasoning_accumulated="内部推理不应展示")

    assert trace is not None
    assert trace.decision_code == "direct_answer"
    assert trace.title == "直接回答"
    assert trace.evidence == []
    assert trace.reasoning_anchor is None
    assert "内部推理" not in (trace.detail or "")



@pytest.mark.asyncio
async def test_persist_after_run_commits_messages_before_optional_summary() -> None:
    db_session = AsyncMock()
    runner = NativeAgentRunner(db_session)
    runner.memory_service.persist_run_messages = AsyncMock()
    runner.memory_service.maybe_update_summary = AsyncMock()

    await runner._persist_after_run(
        conversation_id=uuid4(),
        query="问题",
        run_id=uuid4(),
        final_answer="答案",
        final_content_blocks=None,
        execution_trace=[],
        reasoning_redacted=False,
    )

    runner.memory_service.persist_run_messages.assert_awaited_once()
    runner.memory_service.maybe_update_summary.assert_awaited_once()
    assert db_session.commit.await_count == 2
    db_session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_after_run_keeps_messages_when_optional_summary_fails() -> None:
    db_session = AsyncMock()
    runner = NativeAgentRunner(db_session)
    runner.memory_service.persist_run_messages = AsyncMock()
    runner.memory_service.maybe_update_summary = AsyncMock(side_effect=RuntimeError("summary failed"))

    await runner._persist_after_run(
        conversation_id=uuid4(),
        query="问题",
        run_id=uuid4(),
        final_answer="答案",
        final_content_blocks=None,
        execution_trace=[],
        reasoning_redacted=False,
    )

    runner.memory_service.persist_run_messages.assert_awaited_once()
    runner.memory_service.maybe_update_summary.assert_awaited_once()
    assert db_session.commit.await_count == 1
    db_session.rollback.assert_awaited_once()


def test_tool_result_trace_maps_successful_retrieval_to_knowledge_backed_with_compact_snippet() -> None:
    long_content = "商业模式画布" + "很重要" * 200
    trace = _build_tool_result_trace(
        tool_name="knowledge_retrieval",
        parsed={
            "success": True,
            "tool": "knowledge_retrieval",
            "message": "ok",
            "result_count": 1,
            "evidence_blocks": [
                {
                    "title": "商业模式画布",
                    "content": long_content,
                    "group_type": "courseware",
                    "provenance": [{"page_number": 12}],
                }
            ],
        },
        raw_content="raw tool json should not be shown",
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=9)

    assert trace.answer_basis == "knowledge_backed"
    assert streamed.answer_basis == "knowledge_backed"
    assert persisted["answer_basis"] == "knowledge_backed"
    assert streamed.evidence is not None
    evidence = streamed.evidence[0].model_dump(exclude_none=True)
    assert evidence["title"] == "商业模式画布"
    assert evidence["source_type"] in {"document", "courseware"}
    assert evidence["locator"] in {"第 12 页", "page 12"}
    assert evidence["evidence_type"] in {"courseware", "retrieved_chunk"}
    assert "snippet" in evidence
    assert len(evidence["snippet"]) <= 180
    assert evidence["snippet"] != long_content
    assert persisted["evidence"][0] == evidence


def test_answer_basis_values_cover_direct_retrieval_unavailable_and_evidence_insufficient() -> None:
    direct = _build_direct_answer_trace(query_intent=None, reasoning_accumulated="internal")
    retrieval_unavailable = _build_tool_result_trace(
        tool_name="knowledge_retrieval",
        parsed={
            "success": False,
            "tool": "knowledge_retrieval",
            "message": "知识库检索暂不可用，已切换为直接回答",
            "result_count": 0,
            "retrieval_failed": True,
        },
        raw_content="raw",
    )
    evidence_insufficient = _build_tool_result_trace(
        tool_name="knowledge_retrieval",
        parsed={
            "success": True,
            "tool": "knowledge_retrieval",
            "message": "未命中有效证据",
            "result_count": 0,
            "evidence_blocks": [],
        },
        raw_content="raw",
    )

    assert direct is not None
    assert direct.answer_basis == "direct"
    assert retrieval_unavailable.answer_basis == "retrieval_unavailable"
    assert evidence_insufficient.answer_basis == "evidence_insufficient"
    assert _canonical_trace_to_sse_data(direct).answer_basis == "direct"
    assert _canonical_trace_to_sse_data(retrieval_unavailable).answer_basis == "retrieval_unavailable"
    assert _canonical_trace_to_sse_data(evidence_insufficient).answer_basis == "evidence_insufficient"
