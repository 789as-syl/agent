"""Unit tests for tool result protocol core invariants."""

from __future__ import annotations

import json

from app.tools.result_protocol import TOOL_PROTOCOL_VERSION, build_tool_result, parse_tool_result_payload


def test_build_tool_result_uses_typed_payload_contract() -> None:
    payload = build_tool_result(
        success=True,
        tool="knowledge_retrieval",
        message="ok",
        result_count=2,
        knowledge_points=[{"id": "kp-1"}],
    )

    assert payload["protocol_version"] == TOOL_PROTOCOL_VERSION
    assert payload["protocol_path"] == "typed_payload"
    assert payload["result_count"] == 2
    assert payload["payload"]["knowledge_points"] == [{"id": "kp-1"}]
    assert payload["knowledge_points"] == [{"id": "kp-1"}]


def test_parse_tool_result_payload_normalizes_json_envelope() -> None:
    raw = json.dumps(
        {
            "success": True,
            "tool": "knowledge_retrieval",
            "message": "done",
            "total_count": "3",
            "extra_field": "kept",
        },
        ensure_ascii=False,
    )

    parsed = parse_tool_result_payload(raw)

    assert parsed is not None
    assert parsed["protocol_version"] == TOOL_PROTOCOL_VERSION
    assert parsed["protocol_path"] == "json_string_envelope"
    assert parsed["result_count"] == 3
    assert parsed["extra_field"] == "kept"
    assert parsed["payload"]["extra_field"] == "kept"


def test_parse_tool_result_payload_plain_text_fallback() -> None:
    parsed = parse_tool_result_payload("plain fallback text")

    assert parsed is not None
    assert parsed["success"] is False
    assert parsed["tool"] == "unknown"
    assert parsed["protocol_path"] == "plain_text_fallback"
    assert parsed["message"] == "plain fallback text"
