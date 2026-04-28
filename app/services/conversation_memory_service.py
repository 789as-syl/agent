"""Conversation memory service."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar

from dashscope import Generation
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime.memory_writeback import (
    filter_persisted_assistant_answer,
    filter_persisted_user_query,
)
from app.core.config import settings
from app.core.dashscope_generation import build_dashscope_messages, extract_generation_content
from app.core.log_config import get_logger
from app.models.message import Message
from app.prompts.agent_prompt_catalog import build_memory_summary_prompt
from app.repositories.conversation_memory_repo import ConversationMemoryRepository
from app.repositories.message_repo import MessageRepository

logger = get_logger(__name__)
T = TypeVar("T")

class ConversationMemoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.message_repo = MessageRepository(session)
        self.memory_repo = ConversationMemoryRepository(session)
        self._long_memory_available = True

    async def load_short_memory(self, conversation_id: uuid.UUID) -> list[Message]:
        return await self.message_repo.list_recent_by_conversation(
            conversation_id=conversation_id,
            limit=settings.agent_memory_short_window,
        )

    async def load_long_memory_summary(self, conversation_id: uuid.UUID) -> tuple[str | None, str | None]:
        memory = await self._run_long_memory_op(
            action="read",
            op=lambda: self.memory_repo.get_by_conversation_id(conversation_id),
        )
        if not memory:
            return None, None
        return memory.summary_text, str(memory.last_message_id) if memory.last_message_id else None

    async def maybe_update_summary(self, conversation_id: uuid.UUID) -> tuple[str | None, str | None]:
        memory = await self._run_long_memory_op(
            action="read",
            op=lambda: self.memory_repo.get_by_conversation_id(conversation_id),
        )
        if not self._long_memory_available:
            return None, None

        if memory and memory.last_message_id:
            new_messages = await self.message_repo.list_after_message(conversation_id, memory.last_message_id)
        else:
            new_messages = await self.message_repo.list_all_by_conversation(conversation_id)

        if not new_messages:
            if memory:
                return memory.summary_text, str(memory.last_message_id) if memory.last_message_id else None
            return None, None
        if len(new_messages) < settings.agent_memory_summary_trigger_messages:
            # Keep a minimum message threshold so each turn does not trigger
            # an expensive LLM summary refresh.
            if memory:
                return memory.summary_text, str(memory.last_message_id) if memory.last_message_id else None
            return None, None

        old_summary = memory.summary_text if memory else ""
        summary_text = await self._summarize(old_summary=old_summary, new_messages=new_messages)
        if len(summary_text) > settings.agent_memory_summary_max_chars:
            summary_text = summary_text[: settings.agent_memory_summary_max_chars].rstrip()

        last_message_id = new_messages[-1].id if new_messages else (memory.last_message_id if memory else None)
        summary_version = (memory.summary_version + 1) if memory else 1
        updated = await self._run_long_memory_op(
            action="upsert",
            op=lambda: self.memory_repo.upsert_summary(
                conversation_id=conversation_id,
                summary_text=summary_text,
                summary_version=summary_version,
                last_message_id=last_message_id,
            ),
        )
        if not updated:
            if memory:
                return memory.summary_text, str(memory.last_message_id) if memory.last_message_id else None
            return None, None

        return updated.summary_text, str(updated.last_message_id) if updated.last_message_id else None

    async def _summarize(self, old_summary: str, new_messages: Iterable[Message]) -> str:
        formatted = "\n".join(f"[{m.role}] {m.content}" for m in new_messages)
        prompt = build_memory_summary_prompt(old_summary=old_summary, formatted_new_messages=formatted)
        try:
            response = await self._call_llm(prompt)
            if response:
                return response
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning(f"memory summarize fallback due to llm error: {exc}")

        merged = f"{old_summary}\n{formatted}".strip()
        return merged[: settings.agent_memory_summary_max_chars]

    async def _call_llm(self, prompt: str) -> str:
        result = await asyncio.to_thread(
            Generation.call,
            model=settings.memory_summary_model,
            messages=build_dashscope_messages(prompt),
            stream=False,
            result_format="message",
            temperature=settings.memory_summary_temperature,
            max_tokens=settings.memory_summary_max_tokens,
        )
        if result.status_code != 200:
            raise RuntimeError(f"dashscope summarize failed: {result.code} {result.message}")
        return extract_generation_content(result).strip()

    async def persist_run_messages(
        self,
        conversation_id: uuid.UUID,
        query: str,
        final_answer: str,
        final_content_blocks: list[dict[str, Any]] | None,
        execution_trace: list[dict[str, Any]] | None,
        reasoning_redacted: bool,
        run_id: uuid.UUID,
        client_message_id: str | None = None,
    ) -> None:
        filtered_query = filter_persisted_user_query(query)
        filtered_answer = filter_persisted_assistant_answer(final_answer)
        user_metadata = self._build_user_message_metadata(
            run_id=run_id,
            client_message_id=client_message_id,
        )
        user_message = await self.message_repo.create(
            conversation_id=conversation_id,
            role="user",
            content=filtered_query,
            metadata=user_metadata,
        )
        await self.message_repo.create(
            conversation_id=conversation_id,
            role="assistant",
            content=filtered_answer,
            content_blocks=final_content_blocks,
            metadata=self._build_assistant_message_metadata(
                run_id=run_id,
                user_message_id=user_message.id,
                execution_trace=execution_trace,
                reasoning_redacted=reasoning_redacted,
                client_message_id=client_message_id,
            ),
        )

    def _build_user_message_metadata(
        self,
        *,
        run_id: uuid.UUID,
        client_message_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"run_id": str(run_id)}
        if client_message_id:
            payload["client_message_id"] = client_message_id
        return payload

    def _build_assistant_message_metadata(
        self,
        *,
        run_id: uuid.UUID,
        user_message_id: uuid.UUID,
        execution_trace: list[dict[str, Any]] | None,
        reasoning_redacted: bool,
        client_message_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": str(run_id),
            "reply_to_message_id": str(user_message_id),
            "execution_trace": execution_trace or [],
        }
        if client_message_id:
            payload["client_message_id"] = client_message_id
        if reasoning_redacted:
            # Raw model reasoning is intentionally not persisted as product/API
            # state. Durable transparency is carried by execution_trace; this
            # marker preserves audit evidence that reasoning was redacted
            # without storing chain-of-thought text in message metadata.
            payload["reasoning_redacted"] = True
        return payload

    async def _run_long_memory_op(self, action: str, op: Callable[[], Awaitable[T]]) -> T | None:
        if not self._long_memory_available:
            return None
        try:
            # Use a savepoint so optional long-memory failures do not poison
            # the outer request transaction.
            async with self.session.begin_nested():
                return await op()
        except DBAPIError as exc:
            if self._is_missing_memory_table(exc):
                if self._long_memory_available:
                    logger.warning(
                        "conversation_memories table missing, disable long memory. "
                        "run `alembic upgrade head` to enable summary memory.",
                        action=action,
                    )
                self._long_memory_available = False
                return None
            raise

    def _is_missing_memory_table(self, exc: DBAPIError) -> bool:
        origin_name = getattr(getattr(exc, "orig", None), "__class__", type(None)).__name__
        origin_message = str(getattr(exc, "orig", exc))
        return "UndefinedTableError" in origin_name or (
            'relation "conversation_memories" does not exist' in origin_message
        )

