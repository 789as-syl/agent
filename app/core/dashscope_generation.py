"""DashScope text-generation helpers."""

from __future__ import annotations

from typing import Any


def build_dashscope_messages(prompt: str) -> list[dict[str, str]]:
    """Build a minimal chat-style payload for DashScope-compatible Qwen calls."""

    return [{"role": "user", "content": prompt}]


def extract_generation_content(response: Any) -> str:
    """Read assistant content from DashScope response objects or mocks."""

    output = _get_field(response, "output")
    choices = _get_field(output, "choices")
    if isinstance(choices, list) and choices:
        message = _get_field(choices[0], "message")
        content = _get_field(message, "content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(_coerce_part_text(part) for part in content)
        if content is not None:
            return str(content)

    text = _get_field(output, "text")
    if isinstance(text, str):
        return text
    if text is None:
        return ""
    return str(text)


def _get_field(value: Any, field: str) -> Any:
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)


def _coerce_part_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        text = part.get("text")
        return text if isinstance(text, str) else ""
    text = getattr(part, "text", None)
    return text if isinstance(text, str) else ""
