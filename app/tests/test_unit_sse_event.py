from __future__ import annotations

from app.schemas.sse_event import ExecutionTraceData, FinalAnswerData, SSEEvent


def test_sse_event_to_sse_format_emits_blank_line_delimiter() -> None:
    event = SSEEvent.create_event(
        event_type="final_answer",
        request_id="req-1",
        conversation_id="conv-1",
        step=1,
        trace_data=FinalAnswerData(answer="hello", content_blocks=None),
    )

    payload = event.to_sse_format(include_id=True)

    assert payload.startswith("event: final_answer\n")
    assert f"id: {event.event_id}\n" in payload
    assert payload.endswith("\n\n")


def test_sse_event_to_sse_format_omits_id_when_requested() -> None:
    event = SSEEvent.create_event(
        event_type="final_answer",
        request_id="req-1",
        conversation_id="conv-1",
        step=1,
        trace_data=FinalAnswerData(answer="hello", content_blocks=None),
    )

    payload = event.to_sse_format(include_id=False)

    assert "\nid: " not in payload
    assert payload.endswith("\n\n")


def test_sse_event_model_validate_accepts_legacy_execution_trace_payload() -> None:
    payload = {
        "event_id": "evt-1",
        "request_id": "req-1",
        "conversation_id": "conv-1",
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

    event = SSEEvent.model_validate(payload)

    assert isinstance(event.trace_data, ExecutionTraceData)
    assert event.trace_data.title == "工具返回：knowledge_retrieval"
    assert event.trace_data.result_summary == "legacy summary only"
    assert event.trace_data.decision_code is None


def test_sse_execution_trace_accepts_answer_basis_and_structured_evidence_fields() -> None:
    event = SSEEvent.create_event(
        event_type="execution_trace",
        request_id="req-2",
        conversation_id="conv-1",
        step=2,
        trace_data=ExecutionTraceData(
            kind="tool_result",
            title="知识库命中 1 个证据块",
            status="completed",
            decision_code="retrieval_hit",
            answer_basis="knowledge_backed",
            evidence=[
                {
                    "source": "knowledge_retrieval",
                    "label": "商业模式画布",
                    "title": "商业模式画布",
                    "snippet": "用于描述价值主张、客户细分和收入来源的结构化工具。",
                    "source_type": "courseware",
                    "locator": "page 12",
                    "evidence_type": "retrieved_chunk",
                }
            ],
        ),
    )

    payload = event.model_dump(mode="json")

    assert payload["trace_data"]["answer_basis"] == "knowledge_backed"
    assert payload["trace_data"]["evidence"][0]["title"] == "商业模式画布"
    assert payload["trace_data"]["evidence"][0]["snippet"] == "用于描述价值主张、客户细分和收入来源的结构化工具。"
    assert payload["trace_data"]["evidence"][0]["source_type"] == "courseware"
    assert payload["trace_data"]["evidence"][0]["locator"] == "page 12"
    assert payload["trace_data"]["evidence"][0]["evidence_type"] == "retrieved_chunk"
