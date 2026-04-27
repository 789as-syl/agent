"""Helpers for deriving hidden runtime context inside tools."""

from __future__ import annotations

from typing import Any

from langgraph.prebuilt import ToolRuntime


def build_dialogue_context(runtime: ToolRuntime[Any, Any], *, limit: int = 6) -> str:
    state = runtime.state if isinstance(runtime.state, dict) else {}
    messages = state.get("messages", []) if isinstance(state, dict) else []
    relevant = list(messages or [])[-limit:]
    lines: list[str] = []
    for message in relevant:
        role = getattr(message, "type", None) or getattr(message, "role", None) or message.__class__.__name__.lower()
        content = getattr(message, "content", "")
        text = _message_text(content)
        if not text:
            continue
        if str(role).lower() == "tool":
            continue
        lines.append(f"[{str(role).lower()}] {text}")
    return "\n".join(lines)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return str(content or "").strip()
