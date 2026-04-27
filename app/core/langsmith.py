"""Centralized LangSmith tracing setup and metadata redaction."""

from __future__ import annotations

import os
from typing import Any, cast

from app.core.config import settings

_LANGSMITH_DENY_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "api_key",
    "pending_resume_value",
    "user_id",
    "phone",
    "raw_hitl_payload",
    "raw_edit_payload",
}

_LANGSMITH_ALLOW_KEYS = {
    "conversation_id",
    "run_id",
    "tool_name",
    "event_type",
    "event_status",
    "result_count",
    "hitl_kind",
}


def configure_langsmith() -> bool:
    """Configure LangSmith tracing from settings in one centralized place."""

    enabled = bool(settings.langsmith_tracing and settings.langsmith_api_key)
    os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    if settings.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    return enabled


def langsmith_enabled() -> bool:
    return bool(os.environ.get("LANGSMITH_TRACING", "").lower() == "true")


def build_langsmith_metadata(**kwargs: Any) -> dict[str, Any]:
    return cast(dict[str, Any], scrub_langsmith_metadata(kwargs))


def scrub_langsmith_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in _LANGSMITH_DENY_KEYS:
                continue
            if normalized in _LANGSMITH_ALLOW_KEYS:
                cleaned[str(key)] = scrub_langsmith_metadata(item)
                continue
            cleaned[str(key)] = scrub_langsmith_metadata(item)
        return cleaned
    if isinstance(value, list):
        return [scrub_langsmith_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [scrub_langsmith_metadata(item) for item in value]
    return value


__all__ = [
    "build_langsmith_metadata",
    "configure_langsmith",
    "langsmith_enabled",
    "scrub_langsmith_metadata",
]
