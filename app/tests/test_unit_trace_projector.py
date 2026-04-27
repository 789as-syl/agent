from __future__ import annotations

from types import SimpleNamespace

from app.agents.trace_projector import REDACTION_TEXT, project_run_event, redact_trace_payload


def test_trace_projector_redacts_raw_reasoning_and_provider_payload() -> None:
    payload = {
        "title": "工具完成",
        "raw_reasoning": "secret cot",
        "metadata": {"provider_payload": {"tokens": ["hidden"]}, "safe": "ok"},
        "items": [{"tool_protocol": {"payload": "hidden"}}],
    }

    redacted, changed = redact_trace_payload(payload)

    assert changed is True
    assert redacted["raw_reasoning"] == REDACTION_TEXT
    assert redacted["metadata"]["provider_payload"] == REDACTION_TEXT
    assert redacted["metadata"]["safe"] == "ok"
    assert redacted["items"][0]["tool_protocol"] == REDACTION_TEXT


def test_project_run_event_returns_redacted_admin_timeline_item() -> None:
    row = SimpleNamespace(
        event_id="evt-1",
        event_type="execution_trace",
        step=2,
        sequence_no=3,
        is_final=False,
        event_json={
            "event_id": "evt-1",
            "event_type": "execution_trace",
            "step": 2,
            "timestamp": "2026-04-26T00:00:00Z",
            "trace_data": {
                "kind": "tool_result",
                "title": "知识库检索完成",
                "detail": "命中 1 条证据",
                "status": "completed",
                "metadata": {"raw_reasoning": "hidden", "result_count": 1},
            },
        },
    )

    projected = project_run_event(row)

    assert projected["title"] == "知识库检索完成"
    assert projected["detail_sanitized"] == "命中 1 条证据"
    assert projected["metadata"]["raw_reasoning"] == REDACTION_TEXT
    assert projected["redacted"] is True
