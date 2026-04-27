"""Durable LangGraph checkpoint helpers for the native-only runtime."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_CHECKPOINTER_LOCK = asyncio.Lock()
_CHECKPOINTER: AsyncPostgresSaver | None = None
_CHECKPOINT_POOL: AsyncConnectionPool | None = None
_CHECKPOINTER_READY = False


class CheckpointRuntimeCompatibilityError(RuntimeError):
    """Raised when the current runtime cannot initialize the async checkpoint backend."""


def build_runtime_config(*, thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


async def get_native_checkpointer() -> AsyncPostgresSaver:
    global _CHECKPOINTER, _CHECKPOINT_POOL, _CHECKPOINTER_READY

    if _CHECKPOINTER is not None and _CHECKPOINTER_READY:
        return _CHECKPOINTER

    async with _CHECKPOINTER_LOCK:
        if _CHECKPOINTER is not None and _CHECKPOINTER_READY:
            return _CHECKPOINTER

        _ensure_psycopg_async_runtime_compatible()
        conninfo = _checkpoint_conninfo()
        if _CHECKPOINT_POOL is None:
            _CHECKPOINT_POOL = AsyncConnectionPool(
                conninfo,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                min_size=1,
                max_size=max(4, settings.database_pool_size),
                open=False,
                name="langgraph-checkpoints",
            )
            await _CHECKPOINT_POOL.open()

        _CHECKPOINTER = AsyncPostgresSaver(cast(Any, _CHECKPOINT_POOL))
        if not _CHECKPOINTER_READY:
            await _CHECKPOINTER.setup()
            _CHECKPOINTER_READY = True
        return _CHECKPOINTER


async def close_native_checkpointer() -> None:
    global _CHECKPOINTER, _CHECKPOINT_POOL, _CHECKPOINTER_READY

    _CHECKPOINTER = None
    _CHECKPOINTER_READY = False
    if _CHECKPOINT_POOL is not None:
        await _CHECKPOINT_POOL.close()
        _CHECKPOINT_POOL = None


async def get_checkpoint_tuple(*, thread_id: str) -> CheckpointTuple | None:
    saver = await get_native_checkpointer()
    checkpoint = await saver.aget_tuple(build_runtime_config(thread_id=thread_id))
    return cast(CheckpointTuple | None, checkpoint)


async def get_pending_interrupt(*, thread_id: str) -> dict[str, Any] | None:
    checkpoint_tuple = await get_checkpoint_tuple(thread_id=thread_id)
    return extract_pending_interrupt(checkpoint_tuple)


async def get_checkpoint_messages(*, thread_id: str) -> list[BaseMessage]:
    checkpoint_tuple = await get_checkpoint_tuple(thread_id=thread_id)
    return extract_messages(checkpoint_tuple)


async def get_legacy_run_checkpoint(*, run_id: str) -> CheckpointTuple | None:
    """Diagnostic-only lookup for pre-migration run-keyed checkpoints."""

    return await get_checkpoint_tuple(thread_id=run_id)


def extract_pending_interrupt(checkpoint_tuple: CheckpointTuple | None) -> dict[str, Any] | None:
    if checkpoint_tuple is None:
        return None
    for item in checkpoint_tuple.pending_writes or []:
        if not isinstance(item, tuple) or len(item) != 3:
            continue
        _, channel, value = item
        if channel != "__interrupt__":
            continue
        if isinstance(value, list) and value:
            interrupt_value = getattr(value[0], "value", value[0])
        else:
            interrupt_value = getattr(value, "value", value)
        if isinstance(interrupt_value, dict):
            return dict(interrupt_value)
        return {"value": interrupt_value}
    return None


def extract_messages(checkpoint_tuple: CheckpointTuple | None) -> list[BaseMessage]:
    if checkpoint_tuple is None:
        return []
    checkpoint = checkpoint_tuple.checkpoint or {}
    channel_values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    messages = channel_values.get("messages") if isinstance(channel_values, dict) else None
    if isinstance(messages, list) and all(isinstance(item, BaseMessage) for item in messages):
        return list(messages)
    return []


def _checkpoint_conninfo() -> str:
    raw = (settings.agent_checkpoint_database_url or settings.database_url).strip()
    if raw.startswith("postgresql+asyncpg://"):
        return raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    if raw.startswith("postgresql+psycopg://"):
        return raw.replace("postgresql+psycopg://", "postgresql://", 1)
    if raw.startswith("postgresql://"):
        return raw
    split = urlsplit(raw)
    if split.scheme.startswith("postgresql+"):
        split = split._replace(scheme="postgresql")
        return urlunsplit(split)
    return raw


def is_psycopg_async_runtime_compatible() -> bool:
    """Return whether the current event loop can drive psycopg async connections."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return True

    if sys.platform != "win32":
        return True

    return loop.__class__.__name__ != "ProactorEventLoop"


def _ensure_psycopg_async_runtime_compatible() -> None:
    if is_psycopg_async_runtime_compatible():
        return

    raise CheckpointRuntimeCompatibilityError(
        "LangGraph postgres checkpoints are unavailable on Windows ProactorEventLoop. "
        "Start the API with WindowsSelectorEventLoopPolicy (for example via run_server.py) "
        "or disable eager checkpoint startup."
    )


__all__ = [
    "CheckpointRuntimeCompatibilityError",
    "build_runtime_config",
    "close_native_checkpointer",
    "extract_messages",
    "extract_pending_interrupt",
    "get_checkpoint_messages",
    "get_checkpoint_tuple",
    "get_legacy_run_checkpoint",
    "get_native_checkpointer",
    "get_pending_interrupt",
    "is_psycopg_async_runtime_compatible",
]
