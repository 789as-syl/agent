
from __future__ import annotations

from langchain_core.messages import ToolMessage

from app.agents.native_agent_runner import (
    CanonicalTrace,
    _build_clarification_trace,
    _build_tool_result_trace,
    _canonical_trace_to_entry,
    _canonical_trace_to_sse_data,
    _classify_query_intent,
)
from app.agents.runtime.native_model import format_tool_message_for_model, langchain_messages_to_dashscope
from app.api.conversations import _normalize_execution_trace
from app.tools.result_protocol import build_tool_result, format_tool_result_for_model, sanitize_protocol_mapping

FORBIDDEN = ("success", "tool", "payload", "protocol_version", "error_code", "retrieval_failed")


def assert_no_protocol_fields(text: str) -> None:
    lowered = text.lower()
    for marker in FORBIDDEN:
        assert marker.lower() not in lowered


def test_location_entity_with_innovation_entrepreneurship_is_not_domain() -> None:
    intent = _classify_query_intent("清华大学创新创业大楼在哪")

    assert intent["short_circuit"] is False
    assert intent["reason"] == "fact_lookup"
    assert intent["intent"] == "location_lookup"
    assert intent["matched_signals"] == []


def test_domain_and_business_analysis_intents_are_semantic() -> None:
    canvas = _classify_query_intent("商业模式画布是什么")
    analysis = _classify_query_intent("帮我分析创业项目的商业模式")

    assert canvas["reason"] == "domain"
    assert canvas["intent"] == "domain_qa"
    assert analysis["reason"] == "domain"
    assert analysis["intent"] == "business_analysis"


def test_tool_message_formatter_hides_protocol_json_from_model() -> None:
    payload = build_tool_result(
        success=False,
        tool="knowledge_retrieval",
        message="知识库检索暂不可用，已切换为直接回答",
        result_count=0,
        retrieval_failed=True,
        error_code="RETRIEVAL_PROVIDER_UNAVAILABLE",
        evidence_blocks=[],
    )
    message = ToolMessage(content=payload, tool_call_id="call-1", name="knowledge_retrieval")

    model_text = format_tool_message_for_model(message)
    converted = langchain_messages_to_dashscope([message])[0]["content"]

    assert "知识库检索暂不可用" in model_text
    assert converted == model_text
    assert_no_protocol_fields(model_text)
    assert_no_protocol_fields(converted)


def test_tool_result_formatter_summarizes_success_without_protocol() -> None:
    payload = build_tool_result(
        success=True,
        tool="knowledge_retrieval",
        message="ok",
        result_count=2,
        evidence_blocks=[{"title": "商业模式画布"}, {"title": "价值主张"}],
    )

    text = format_tool_result_for_model(payload, tool_name="knowledge_retrieval")

    assert "命中 2 条证据" in text
    assert "商业模式画布" in text
    assert_no_protocol_fields(text)


def test_trace_semantic_key_and_metadata_are_safe() -> None:
    trace = _build_tool_result_trace(
        tool_name="knowledge_retrieval",
        parsed={
            "success": False,
            "tool": "knowledge_retrieval",
            "message": "知识库检索暂不可用，已切换为直接回答",
            "result_count": 0,
            "retrieval_failed": True,
            "payload": {"error_code": "RETRIEVAL_PROVIDER_UNAVAILABLE"},
            "error_code": "RETRIEVAL_PROVIDER_UNAVAILABLE",
        },
        raw_content={"success": False, "tool": "knowledge_retrieval"},
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=1)

    assert streamed.semantic_key == persisted["semantic_key"]
    assert streamed.retrieval_failed is None
    serialized = str(streamed.model_dump()) + str(persisted)
    assert "payload" not in serialized
    assert "error_code" not in serialized
    assert "retrieval_failed': True" not in serialized


def test_sanitize_protocol_mapping_drops_nested_protocol_fields() -> None:
    cleaned = sanitize_protocol_mapping(
        {
            "payload": {"error_code": "X"},
            "tool_name": "knowledge_retrieval",
            "nested": {"protocol_version": "native-v1", "safe": "ok"},
        }
    )

    assert cleaned == {"tool_name": "knowledge_retrieval", "nested": {"safe": "ok"}}


def test_canonical_trace_semantic_key_distinguishes_tool_inputs() -> None:
    left = CanonicalTrace(
        kind="tool_call",
        title="调用工具",
        status="running",
        decision_code="tool_call_web_search",
        tool_name="web_search",
        tool_input={"query": "A"},
    )
    right = CanonicalTrace(
        kind="tool_call",
        title="调用工具",
        status="running",
        decision_code="tool_call_web_search",
        tool_name="web_search",
        tool_input={"query": "B"},
    )

    assert _canonical_trace_to_entry(left, step=1)["semantic_key"] != _canonical_trace_to_entry(right, step=2)["semantic_key"]



def test_history_trace_normalization_preserves_semantic_key_and_cleans_metadata() -> None:
    normalized = _normalize_execution_trace(
        [
            {
                "id": "old-1",
                "semantic_key": "tool_result:retrieval_failed:knowledge_retrieval:0:completed",
                "kind": "tool_result",
                "title": "知识库检索失败",
                "status": "completed",
                "metadata": {
                    "payload": {"error_code": "X"},
                    "retrieval_failed": True,
                    "tool_name": "knowledge_retrieval",
                },
            }
        ],
        default_timestamp=123,
    )

    assert normalized is not None
    assert normalized[0]["semantic_key"] == "tool_result:retrieval_failed:knowledge_retrieval:0:completed"
    assert normalized[0]["metadata"] == {"tool_name": "knowledge_retrieval"}


def test_clarification_trace_uses_needs_clarification_answer_basis() -> None:
    trace = _build_clarification_trace(
        interrupt_value={
            "action_requests": [
                {"name": "request_human_input", "args": {"prompt": "请补充项目阶段", "kind": "input"}}
            ],
            "review_configs": [{"allowed_decisions": ["edit", "reject"]}],
        },
        reasoning_accumulated="internal reasoning must not leak",
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=3)

    assert trace.answer_basis == "needs_clarification"
    assert streamed.answer_basis == "needs_clarification"
    assert persisted["answer_basis"] == "needs_clarification"
    assert "internal reasoning" not in str(streamed.model_dump())
    assert "internal reasoning" not in str(persisted)


def test_retrieval_failed_label_stays_internal_when_trace_is_serialized() -> None:
    trace = _build_tool_result_trace(
        tool_name="knowledge_retrieval",
        parsed={
            "success": False,
            "tool": "knowledge_retrieval",
            "message": "知识库检索暂不可用，已切换为直接回答",
            "result_count": 0,
            "retrieval_failed": True,
            "payload": {"error_code": "RETRIEVAL_PROVIDER_UNAVAILABLE"},
        },
        raw_content={"success": False, "tool": "knowledge_retrieval"},
    )

    streamed = _canonical_trace_to_sse_data(trace)
    persisted = _canonical_trace_to_entry(trace, step=4)

    assert streamed.answer_basis == "retrieval_unavailable"
    assert persisted["answer_basis"] == "retrieval_unavailable"
    assert streamed.decision_code == "retrieval_unavailable"
    assert persisted["decision_code"] == "retrieval_unavailable"
    serialized_user_payload = str(streamed.model_dump(exclude_none=True)) + str(persisted)
    assert "retrieval_failed': True" not in serialized_user_payload
    assert "payload" not in serialized_user_payload
    assert "error_code" not in serialized_user_payload
