"""核心基础设施模块：trace_context。"""

from __future__ import annotations

from typing import Any


def build_trace_log_context(
    *,
    request_id: str | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
    event_type: str | None = None,
    stage: str | None = None,
) -> dict[str, str]:
    context: dict[str, str] = {}
    if request_id:
        context["request_id"] = str(request_id)
    if conversation_id:
        context["conversation_id"] = str(conversation_id)
    if run_id:
        context["run_id"] = str(run_id)
    if user_id:
        context["user_id"] = str(user_id)
    if event_type:
        context["event_type"] = str(event_type)
    if stage:
        context["stage"] = str(stage)
    return context


def merge_trace_log_context(base: dict[str, Any], **extras: Any) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extras.items():
        if value is None:
            continue
        merged[key] = value
    return merged
