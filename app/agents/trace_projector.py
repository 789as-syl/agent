"""Redacted trace projection for admin and message audit surfaces."""

from __future__ import annotations

from typing import Any

FORBIDDEN_TRACE_KEYS = {
    "raw_reasoning",
    "reasoning_content",
    "chain_of_thought",
    "cot",
    "provider_payload",
    "provider_response",
    "tool_protocol",
    "protocol_version",
    "payload",
    "messages",
    "raw_messages",
}
FORBIDDEN_TEXT_MARKERS = ("raw_reasoning", "reasoning_content", "chain_of_thought", "provider_payload")
REDACTION_TEXT = "[redacted internal trace payload]"


def _is_forbidden_key(key: str) -> bool:
    normalized = key.lower().strip()
    return normalized in FORBIDDEN_TRACE_KEYS or normalized.startswith("raw_")


def redact_trace_payload(value: Any) -> tuple[Any, bool]:
    """Return a JSON-safe redacted copy and whether anything was removed."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        changed = False
        for key, item in value.items():
            if _is_forbidden_key(str(key)):
                redacted[str(key)] = REDACTION_TEXT
                changed = True
                continue
            next_value, next_changed = redact_trace_payload(item)
            redacted[str(key)] = next_value
            changed = changed or next_changed
        return redacted, changed
    if isinstance(value, list):
        items: list[Any] = []
        changed = False
        for item in value:
            next_value, next_changed = redact_trace_payload(item)
            items.append(next_value)
            changed = changed or next_changed
        return items, changed
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in FORBIDDEN_TEXT_MARKERS):
            return REDACTION_TEXT, True
    return value, False


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def project_run_event(row: Any) -> dict[str, Any]:
    """Project a persisted RunEvent row into a redacted admin timeline item."""
    event_json = dict(getattr(row, "event_json", None) or {})
    trace_data = event_json.get("trace_data") if isinstance(event_json.get("trace_data"), dict) else {}
    assert isinstance(trace_data, dict)
    safe_trace, redacted = redact_trace_payload(trace_data)
    if not isinstance(safe_trace, dict):
        safe_trace = {}

    event_type = str(getattr(row, "event_type", None) or event_json.get("event_type") or "unknown")
    title = _string_or_none(safe_trace.get("title")) or _default_title(event_type)
    detail = _string_or_none(safe_trace.get("detail")) or _string_or_none(safe_trace.get("result_summary"))
    metadata = safe_trace.get("metadata") if isinstance(safe_trace.get("metadata"), dict) else {}
    safe_metadata, metadata_redacted = redact_trace_payload(metadata)
    return {
        "event_id": str(getattr(row, "event_id", None) or event_json.get("event_id") or ""),
        "event_type": event_type,
        "step": int(getattr(row, "step", None) or event_json.get("step") or 0),
        "sequence_no": getattr(row, "sequence_no", None),
        "timestamp": _string_or_none(event_json.get("timestamp")),
        "title": title,
        "kind": str(safe_trace.get("kind") or event_type),
        "status": str(safe_trace.get("status") or ("completed" if getattr(row, "is_final", False) else "running")),
        "detail_sanitized": detail,
        "metadata": safe_metadata if isinstance(safe_metadata, dict) else {},
        "redacted": bool(redacted or metadata_redacted or event_type == "reasoning_delta"),
    }


def project_sse_event_dict(event_json: dict[str, Any]) -> dict[str, Any]:
    """Project an event-like dict without requiring an ORM row."""
    class _Row:
        def __init__(self, payload: dict[str, Any]):
            self.event_json = payload
            self.event_id = payload.get("event_id")
            self.event_type = payload.get("event_type")
            self.step = payload.get("step")
            self.sequence_no = None
            self.is_final = payload.get("is_final", False)

    return project_run_event(_Row(event_json))


def _default_title(event_type: str) -> str:
    return {
        "execution_trace": "执行过程",
        "reasoning_delta": "模型推理片段（已脱敏）",
        "generation_delta": "回答生成片段",
        "final_answer": "最终回答",
        "hitl_requested": "等待人工确认",
        "hitl_resolved": "人工确认完成",
        "error": "运行错误",
        "done": "运行结束",
    }.get(event_type, event_type)
