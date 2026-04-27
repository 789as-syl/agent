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
