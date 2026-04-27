"""Contract helpers for Agent/Trace replay and durable history boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel

from app.schemas.sse_event import SSEEvent
from app.tools.result_protocol import DURABLE_HISTORY_FORBIDDEN_KEYS

TRUTH_SOURCE_CONTRACT: dict[str, dict[str, str]] = {
    "checkpoint": {
        "owns": "LangGraph runtime continuation state, pending interrupts, and resumable graph messages.",
        "does_not_own": "User-visible durable history, audit replay, or product transcript semantics.",
    },
    "run_events": {
        "owns": "Append-only run transcript for SSE playback, audit, retry diagnostics, and trace reconstruction.",
        "does_not_own": "Runtime continuation or canonical user-visible conversation history.",
    },
    "messages": {
        "owns": "Final user-visible conversation history and sanitized assistant answer/trace summaries.",
        "does_not_own": "Raw event streams, checkpoint continuation state, or raw chain-of-thought.",
    },
}

VOLATILE_REPLAY_FIELDS: frozenset[str] = frozenset(
    {
        "event_id",
        "timestamp",
        "step_id",
        "generated_step_id",
    }
)


def normalize_sse_event_for_replay(event: SSEEvent | Mapping[str, Any]) -> dict[str, Any]:
    """Return a semantic replay representation with volatile identifiers removed."""

    payload = _to_plain_mapping(event)
    return cast(dict[str, Any], _drop_volatile_replay_fields(payload))


def find_durable_history_contract_leaks(payload: Mapping[str, Any]) -> list[str]:
    """Return dotted paths that would leak raw reasoning or protocol internals to history APIs."""

    leaks: list[str] = []
    _collect_forbidden_paths(payload, path="", leaks=leaks)
    return leaks


def _to_plain_mapping(event: SSEEvent | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(event, SSEEvent):
        return event.model_dump(mode="python", exclude_none=True)
    return dict(event)


def _drop_volatile_replay_fields(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python", exclude_none=True)
    if isinstance(value, Mapping):
        return {
            str(key): _drop_volatile_replay_fields(item)
            for key, item in value.items()
            if str(key) not in VOLATILE_REPLAY_FIELDS
        }
    if isinstance(value, list):
        return [_drop_volatile_replay_fields(item) for item in value]
    return value


def _collect_forbidden_paths(value: Any, *, path: str, leaks: list[str]) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python", exclude_none=True)
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in DURABLE_HISTORY_FORBIDDEN_KEYS:
                leaks.append(child_path)
            _collect_forbidden_paths(item, path=child_path, leaks=leaks)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            _collect_forbidden_paths(item, path=child_path, leaks=leaks)
