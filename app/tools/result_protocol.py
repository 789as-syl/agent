"""Structured tool result helpers used by the native business shell."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field

TOOL_PROTOCOL_VERSION = "native-v1"
VALID_PROTOCOL_PATHS = {"typed_payload", "json_string_envelope", "plain_text_fallback"}
_RESERVED_KEYS = {
    "success",
    "tool",
    "message",
    "result_count",
    "retrieval_failed",
    "protocol_version",
    "protocol_path",
    "payload",
}


class ToolExecutionResult(BaseModel):
    success: bool
    tool: str
    message: str
    result_count: int = 0
    retrieval_failed: bool = False
    protocol_version: str = TOOL_PROTOCOL_VERSION
    protocol_path: str = Field(default="typed_payload")
    payload: dict[str, Any] = Field(default_factory=dict)


def build_tool_result(
    *,
    success: bool,
    tool: str,
    message: str,
    result_count: int = 0,
    retrieval_failed: bool = False,
    protocol_path: str = "typed_payload",
    **extra: Any,
) -> dict[str, Any]:
    base = ToolExecutionResult(
        success=success,
        tool=tool,
        message=message,
        result_count=result_count,
        retrieval_failed=retrieval_failed,
        protocol_path=protocol_path,
        payload=dict(extra),
    ).model_dump(mode="python")
    return {**base, **extra}


def serialize_tool_result(
    *,
    success: bool,
    tool: str,
    message: str,
    result_count: int = 0,
    retrieval_failed: bool = False,
    **extra: Any,
) -> str:
    return json.dumps(
        build_tool_result(
            success=success,
            tool=tool,
            message=message,
            result_count=result_count,
            retrieval_failed=retrieval_failed,
            protocol_path="json_string_envelope",
            **extra,
        ),
        ensure_ascii=False,
    )


DURABLE_HISTORY_FORBIDDEN_KEYS = frozenset(
    {
        "success",
        "tool",
        "payload",
        "protocol_version",
        "protocol_path",
        "retrieval_failed",
        "error",
        "error_code",
        "raw_cot",
        "raw_chain_of_thought",
        "chain_of_thought",
        "raw_reasoning",
        "reasoning_content",
        "provider_response",
        "tool_call_payload",
        "evidence_blocks",
        "anchor_chunk_indices",
        "provenance",
        "score",
        "similarity",
        "rerank_score",
    }
)

FORBIDDEN_PROTOCOL_KEYS = DURABLE_HISTORY_FORBIDDEN_KEYS


def format_tool_result_for_model(content: Any, *, tool_name: str | None = None) -> str:
    """Return a natural-language tool observation safe to send to the model.

    The structured tool protocol is for program control only.  This formatter is
    the single model-facing boundary and intentionally never serializes the raw
    JSON envelope, payload, provider errors, or protocol fields.
    """

    parsed = parse_tool_result_payload(content)
    if not parsed:
        return "工具已执行完成。请根据已知上下文继续回答，不要复述工具内部数据。"

    name = str(tool_name or parsed.get("tool") or "unknown")
    success = bool(parsed.get("success", not parsed.get("retrieval_failed", False)))
    result_count = _coerce_result_count(parsed)
    retrieval_failed = bool(parsed.get("retrieval_failed", False))
    message = _safe_tool_message(parsed.get("message"))

    if name == "knowledge_retrieval":
        if retrieval_failed or not success:
            return "知识库检索暂不可用。请不要复述工具结果、JSON 或错误码；可基于通用知识直接回答，并在缺少资料时说明无法基于知识库验证。"
        evidence_blocks = parsed.get("evidence_blocks")
        titles = _safe_titles(evidence_blocks, fallback_keys=("title", "knowledge_point_id"))
        if titles:
            return f"知识库检索命中 {result_count} 条证据：{'；'.join(titles[:3])}。请基于证据回答，不要复述工具协议。"
        return f"知识库检索完成，命中 {result_count} 条证据。请基于证据回答，不要复述工具协议。"

    if name == "web_search":
        if not success:
            return "外部搜索暂不可用。请不要复述工具结果、JSON 或错误信息；可基于已有知识回答，并说明无法实时验证。"
        titles = _safe_titles(parsed.get("results"), fallback_keys=("title",))
        if titles:
            return f"外部搜索返回 {result_count} 条结果：{'；'.join(titles[:3])}。请综合这些结果回答，不要复述工具协议。"
        return f"外部搜索完成，返回 {result_count} 条结果。请综合结果回答，不要复述工具协议。"

    if name == "math_calculator":
        if success and "result" in parsed:
            return f"计算工具已完成，结果为：{parsed.get('result')}。请用自然语言给出结论。"
        return "计算工具暂时无法完成本次计算。请不要复述工具错误；可说明计算失败并给出可检查的表达式。"

    if success:
        if message:
            return f"工具已执行完成：{message}。请用自然语言继续回答，不要复述工具协议。"
        return "工具已执行完成。请用自然语言继续回答，不要复述工具协议。"
    return "工具暂不可用。请不要复述工具结果、JSON 或错误信息；可基于已有上下文继续回答。"


def sanitize_protocol_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """Drop protocol/debug fields from user-facing metadata dictionaries."""

    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key in FORBIDDEN_PROTOCOL_KEYS:
            continue
        if key == "metadata" and isinstance(item, dict):
            nested = sanitize_protocol_mapping(item)
            if nested:
                sanitized[key] = nested
            continue
        if isinstance(item, dict):
            nested = sanitize_protocol_mapping(item)
            if nested:
                sanitized[key] = nested
        elif isinstance(item, list):
            cleaned_list = []
            for element in item:
                if isinstance(element, dict):
                    cleaned = sanitize_protocol_mapping(element)
                    if cleaned:
                        cleaned_list.append(cleaned)
                else:
                    cleaned_list.append(element)
            if cleaned_list:
                sanitized[key] = cleaned_list
        else:
            sanitized[key] = item
    return sanitized


def _safe_tool_message(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    forbidden_markers = ("ConnectionResetError", "Traceback", "DashScope", "protocol_version", "payload")
    if any(marker in text for marker in forbidden_markers):
        return ""
    return text[:200]


def _safe_titles(value: Any, *, fallback_keys: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list):
        return []
    titles: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        for key in fallback_keys:
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                titles.append(raw.strip()[:80])
                break
    return titles


def parse_tool_result_payload(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return _normalize_payload(content, protocol_path="typed_payload")

    text = _coerce_content_to_text(content)
    if text is None:
        return None

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return _build_fallback_payload(message=text, protocol_path="plain_text_fallback")

    if not isinstance(raw, dict):
        return _build_fallback_payload(message=str(raw), protocol_path="plain_text_fallback")

    return _normalize_payload(raw, protocol_path="json_string_envelope")


def _coerce_content_to_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item if isinstance(item, str) else str(item) for item in content)
    return None


def _normalize_payload(raw: dict[str, Any], *, protocol_path: str) -> dict[str, Any]:
    payload = cast(dict[str, Any], raw.get("payload")) if isinstance(raw.get("payload"), dict) else {}
    extra = {
        **payload,
        **{key: value for key, value in raw.items() if key not in _RESERVED_KEYS},
    }
    base = ToolExecutionResult(
        success=bool(raw.get("success", not raw.get("retrieval_failed", False))),
        tool=str(raw.get("tool") or "unknown"),
        message=str(raw.get("message") or "tool finished"),
        result_count=_coerce_result_count(raw),
        retrieval_failed=bool(raw.get("retrieval_failed", False)),
        protocol_version=str(raw.get("protocol_version") or TOOL_PROTOCOL_VERSION),
        protocol_path=str(raw.get("protocol_path") or protocol_path)
        if str(raw.get("protocol_path") or protocol_path) in VALID_PROTOCOL_PATHS
        else protocol_path,
        payload=extra,
    ).model_dump(mode="python")
    return {**base, **extra}


def _coerce_result_count(raw: dict[str, Any]) -> int:
    value = raw.get("result_count", raw.get("total_count", 0))
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_fallback_payload(*, message: str, protocol_path: str) -> dict[str, Any]:
    return ToolExecutionResult(
        success=False,
        tool="unknown",
        message=message,
        result_count=0,
        protocol_path=protocol_path,
        payload={},
    ).model_dump(mode="python")
