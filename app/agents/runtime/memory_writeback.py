"""Stable writeback filtering for persisted conversation memory."""

from __future__ import annotations

import re
from typing import Any


def filter_persisted_user_query(query: str) -> str:
    return str(query or "").strip()


def filter_persisted_assistant_answer(answer: str) -> str:
    return sanitize_assistant_answer(answer)


_TOOL_RESULT_JSON_PREFIX_RE = re.compile(
    r'^\s*\{\s*"success"\s*:\s*false\s*,\s*"tool"\s*:\s*"knowledge_retrieval".*?\}\s*',
    re.DOTALL,
)

_TOOL_RESULT_JSON_LINE_RE = re.compile(
    r'^\s*\{.*?"tool"\s*:\s*"knowledge_retrieval".*?\}\s*$',
    re.MULTILINE,
)


def sanitize_assistant_answer(answer: str) -> str:
    text = str(answer or "")
    text = _remove_balanced_tool_json_prefix(text)
    text = _TOOL_RESULT_JSON_PREFIX_RE.sub("", text)
    text = _TOOL_RESULT_JSON_LINE_RE.sub("", text)
    return text.lstrip()


def _remove_balanced_tool_json_prefix(text: str) -> str:
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return text

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(stripped):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[: index + 1]
                if _looks_like_tool_protocol_json(candidate):
                    return stripped[index + 1 :]
                return text

    # Streaming deltas can arrive before the protocol JSON prefix is complete.
    # Never render the partial envelope while waiting for the closing brace.
    if _looks_like_tool_protocol_json(stripped):
        return ""
    return text


def _looks_like_tool_protocol_json(value: str) -> bool:
    markers = (
        '"tool"',
        '"success"',
        '"protocol_version"',
        '"protocol_path"',
        '"retrieval_failed"',
        '"payload"',
        'knowledge_retrieval',
    )
    return any(marker in value for marker in markers)


def filter_persisted_sources(sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        filtered.append(
            {
                "knowledge_point_id": item.get("knowledge_point_id"),
                "title": item.get("title"),
                "score": item.get("score"),
            }
        )
    return filtered
