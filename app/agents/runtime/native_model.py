"""LangChain-compatible DashScope chat model for create_agent."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from typing import Any, Literal

from dashscope import Generation
from dashscope.aigc.generation import AioGeneration
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

from app.core.config import settings
from app.core.log_config import get_logger
from app.tools.result_protocol import format_tool_result_for_model

REQUEST_HUMAN_INPUT_TOOL_NAME = "request_human_input"
ContentValue = str | list[str | dict[str, Any]]
logger = get_logger(__name__)


class DashScopeAgentChatModel(BaseChatModel):
    """Minimal DashScope-backed chat model that supports LangChain tool binding."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model_name: str = Field(default="qwen-turbo")
    temperature: float = Field(default=0.3)
    max_tokens: int = Field(default=1200)
    bound_tools: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    bound_tool_choice: str | None = Field(default=None, exclude=True)

    @property
    def _llm_type(self) -> str:
        return "dashscope"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> DashScopeAgentChatModel:
        del kwargs
        schemas = [convert_to_openai_tool(tool) for tool in tools]
        return self.model_copy(update={"bound_tools": schemas, "bound_tool_choice": tool_choice})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        message = self._call_dashscope(messages)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        message = await asyncio.to_thread(self._call_dashscope, messages)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        del stop, run_manager, kwargs
        previous_text = ""
        previous_tool_args: dict[int, str] = {}
        previous_reasoning = ""
        emitted_any_chunk = False

        response_stream = Generation.call(
            model=self.model_name,
            messages=langchain_messages_to_dashscope(messages),
            tools=self.bound_tools or None,
            result_format="message",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            incremental_output=True,
            **_thinking_kwargs(),
        )

        for response in response_stream:
            chunk = _generation_response_to_chunk(
                response=response,
                previous_text=previous_text,
                previous_tool_args=previous_tool_args,
                previous_reasoning=previous_reasoning,
                is_stream_final=_is_generation_stream_final(response),
            )
            if chunk is None:
                continue
            previous_text = chunk["current_text"]
            previous_reasoning = chunk["current_reasoning"]
            _log_stream_chunk(
                answer_delta=chunk["answer_delta"],
                reasoning_delta=chunk["reasoning_delta"],
                tool_call_chunks=len(chunk["payload"].message.tool_call_chunks),
                chunk_position=getattr(chunk["payload"].message, "chunk_position", None),
            )
            emitted_any_chunk = True
            yield chunk["payload"]

        if not emitted_any_chunk:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", chunk_position="last"))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        del stop, run_manager, kwargs
        previous_text = ""
        previous_tool_args: dict[int, str] = {}
        previous_reasoning = ""
        emitted_any_chunk = False

        response_stream = await AioGeneration.call(
            model=self.model_name,
            messages=langchain_messages_to_dashscope(messages),
            tools=self.bound_tools or None,
            result_format="message",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            incremental_output=True,
            **_thinking_kwargs(),
        )

        async for response in response_stream:
            chunk = _generation_response_to_chunk(
                response=response,
                previous_text=previous_text,
                previous_tool_args=previous_tool_args,
                previous_reasoning=previous_reasoning,
                is_stream_final=_is_generation_stream_final(response),
            )
            if chunk is None:
                continue
            previous_text = chunk["current_text"]
            previous_reasoning = chunk["current_reasoning"]
            _log_stream_chunk(
                answer_delta=chunk["answer_delta"],
                reasoning_delta=chunk["reasoning_delta"],
                tool_call_chunks=len(chunk["payload"].message.tool_call_chunks),
                chunk_position=getattr(chunk["payload"].message, "chunk_position", None),
            )
            emitted_any_chunk = True
            yield chunk["payload"]

        if not emitted_any_chunk:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", chunk_position="last"))

    def _call_dashscope(self, messages: list[BaseMessage]) -> AIMessage:
        response = Generation.call(
            model=self.model_name,
            messages=langchain_messages_to_dashscope(messages),
            tools=self.bound_tools or None,
            result_format="message",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **_thinking_kwargs(),
        )
        if getattr(response, "status_code", None) != 200:
            raise RuntimeError(f"dashscope native model failed: {getattr(response, 'message', 'unknown error')}")
        return parse_dashscope_response_to_ai_message(response)


def langchain_messages_to_dashscope(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Convert LangChain messages into DashScope chat messages."""

    converted: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            converted.append({"role": "system", "content": serialize_content_for_dashscope(message.content)})
        elif isinstance(message, HumanMessage):
            converted.append({"role": "user", "content": serialize_content_for_dashscope(message.content)})
        elif isinstance(message, ToolMessage):
            converted.append(
                {
                    "role": "tool",
                    "content": format_tool_message_for_model(message),
                    "tool_call_id": message.tool_call_id,
                    "name": message.name,
                }
            )
        elif isinstance(message, AIMessage):
            payload: dict[str, Any] = {"role": "assistant", "content": serialize_content_for_dashscope(message.content)}
            tool_calls = list(getattr(message, "tool_calls", []) or [])
            if tool_calls:
                payload["tool_calls"] = [
                    {
                        "id": str(call.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(call.get("name") or ""),
                            "arguments": json.dumps(call.get("args") or {}, ensure_ascii=False),
                        },
                    }
                    for call in tool_calls
                ]
            converted.append(payload)
    return converted


def parse_dashscope_response_to_ai_message(response: Any) -> AIMessage:
    """Parse DashScope chat completion response into an AIMessage."""

    output = getattr(response, "output", None)
    choices = getattr(output, "choices", None) if output is not None else None
    choice = choices[0] if isinstance(choices, list) and choices else None
    if choice is None:
        raise ValueError("DashScope response did not include choices")

    message = getattr(choice, "message", None)
    if message is None and isinstance(choice, dict):
        message = choice.get("message")
    if message is None:
        raise ValueError("DashScope choice did not include a message")

    content = _coerce_content(_message_field(message, "content"))
    tool_calls = _message_field(message, "tool_calls")
    normalized_tool_calls = [_normalize_tool_call(item) for item in (tool_calls or []) if item]
    normalized_tool_calls = [item for item in normalized_tool_calls if item is not None]
    reasoning_payload = _extract_reasoning_payload(choice=choice, message=message)
    additional_kwargs: dict[str, Any] = {}
    if reasoning_payload["text"]:
        additional_kwargs = {
            "reasoning_delta": reasoning_payload["text"],
            "reasoning_accumulated": reasoning_payload["text"],
            "reasoning_source": reasoning_payload["source"],
        }
    return AIMessage(content=content, tool_calls=normalized_tool_calls, additional_kwargs=additional_kwargs)


def message_content_to_text(content: ContentValue | Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


def message_content_to_blocks(content: ContentValue | Any) -> list[dict[str, Any]] | None:
    if not isinstance(content, list):
        return None
    blocks: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            blocks.append({"type": "text", "text": item})
        elif isinstance(item, dict):
            blocks.append(dict(item))
        else:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                blocks.append({"type": getattr(item, "type", "text"), "text": text})
    return blocks or None


def serialize_content_for_dashscope(content: ContentValue | Any) -> str:
    return message_content_to_text(content)


def format_tool_message_for_model(message: ToolMessage) -> str:
    """Format ToolMessage content for the LLM without exposing tool protocol JSON."""

    content = getattr(message, "artifact", None) or message.content
    return format_tool_result_for_model(content, tool_name=message.name)


def _generation_response_to_chunk(
    *,
    response: Any,
    previous_text: str,
    previous_tool_args: dict[int, str],
    previous_reasoning: str,
    is_stream_final: bool = False,
) -> dict[str, Any] | None:
    output = getattr(response, "output", None)
    choices = getattr(output, "choices", None) if output is not None else None
    choice = choices[0] if isinstance(choices, list) and choices else None
    if choice is None:
        return None

    message = getattr(choice, "message", None)
    if message is None and isinstance(choice, dict):
        message = choice.get("message")

    current_text = message_content_to_text(_message_field(message, "content"))
    delta_text = (
        current_text[len(previous_text):]
        if current_text.startswith(previous_text)
        else current_text
    )
    reasoning_payload = _extract_reasoning_payload(choice=choice, message=message)
    current_reasoning = reasoning_payload["text"]
    delta_reasoning = (
        current_reasoning[len(previous_reasoning):]
        if current_reasoning.startswith(previous_reasoning)
        else current_reasoning
    )

    raw_tool_calls = _message_field(message, "tool_calls") or []
    tool_call_chunks = []
    for index, raw_call in enumerate(raw_tool_calls):
        function_payload = _message_field(raw_call, "function") or {}
        if not isinstance(function_payload, dict):
            function_payload = {
                "name": getattr(function_payload, "name", None),
                "arguments": getattr(function_payload, "arguments", None),
            }
        current_args = str(function_payload.get("arguments") or "")
        previous_args = previous_tool_args.get(index, "")
        delta_args = current_args[len(previous_args):] if current_args.startswith(previous_args) else current_args
        first_tool_chunk = index not in previous_tool_args
        previous_tool_args[index] = current_args
        tool_call_chunks.append(
            tool_call_chunk(
                name=(str(function_payload.get("name") or "") or None) if first_tool_chunk else None,
                args=delta_args or None,
                id=(str(_message_field(raw_call, "id") or "") or None) if first_tool_chunk else None,
                index=index,
            )
        )

    finish_reason = _message_field(choice, "finish_reason")
    chunk_position: Literal["last"] | None = (
        "last" if is_stream_final or _is_terminal_finish_reason(finish_reason) else None
    )
    if not delta_text and not delta_reasoning and not tool_call_chunks and chunk_position is None:
        return None

    payload = ChatGenerationChunk(
        message=AIMessageChunk(
            content=delta_text,
            tool_call_chunks=tool_call_chunks,
            chunk_position=chunk_position,
            additional_kwargs={
                "reasoning_delta": delta_reasoning,
                "reasoning_accumulated": current_reasoning,
                "reasoning_source": reasoning_payload["source"],
            },
        )
    )
    return {
        "payload": payload,
        "current_text": current_text,
        "current_reasoning": current_reasoning,
        "answer_delta": delta_text,
        "reasoning_delta": delta_reasoning,
    }


def _is_terminal_finish_reason(finish_reason: Any) -> bool:
    if finish_reason is None:
        return False
    text = str(finish_reason).strip().lower()
    return text in {"stop", "tool_calls", "length", "content_filter", "finished", "finish"}


def _is_generation_stream_final(response: Any) -> bool:
    for attr in ("is_end", "is_final", "is_finished"):
        value = _safe_field(response, attr)
        if isinstance(value, bool):
            return value
    output = _safe_field(response, "output")
    for attr in ("is_end", "is_final", "is_finished"):
        value = _safe_field(output, attr) if output is not None else None
        if isinstance(value, bool):
            return value
    return False


def _safe_field(value: Any, field: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(field)
    try:
        return getattr(value, field, None)
    except (AttributeError, KeyError, TypeError):
        return None


def _message_field(message: Any, field: str) -> Any:
    return _safe_field(message, field)


def _normalize_tool_call(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    call_id = _message_field(raw, "id") or ""
    function_payload = _message_field(raw, "function") or {}
    if not isinstance(function_payload, dict):
        function_payload = {
            "name": getattr(function_payload, "name", None),
            "arguments": getattr(function_payload, "arguments", None),
        }
    name = str(function_payload.get("name") or "").strip()
    raw_arguments = function_payload.get("arguments")
    if not name:
        return None
    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) and raw_arguments else {}
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return {
        "id": str(call_id),
        "name": name,
        "args": arguments,
        "type": "tool_call",
    }


def _coerce_content(content: Any) -> ContentValue:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks: list[str | dict[str, Any]] = []
        for item in content:
            if isinstance(item, str):
                blocks.append(item)
            elif isinstance(item, dict):
                blocks.append(dict(item))
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    blocks.append({"type": getattr(item, "type", "text"), "text": text})
        return blocks
    return str(content or "")


def _extract_reasoning_payload(*, choice: Any, message: Any) -> dict[str, str]:
    candidates = [
        ("reasoning_content", _message_field(message, "reasoning_content")),
        ("thinking_content", _message_field(message, "thinking_content")),
        ("reasoning", _message_field(message, "reasoning")),
    ]
    delta = _message_field(choice, "delta")
    if delta:
        candidates.extend(
            [
                ("reasoning_content", _message_field(delta, "reasoning_content")),
                ("thinking_content", _message_field(delta, "thinking_content")),
                ("reasoning", _message_field(delta, "reasoning")),
            ]
        )

    for source, value in candidates:
        text = message_content_to_text(value)
        if text:
            return {"source": source, "text": text}
    return {"source": "", "text": ""}


def _thinking_kwargs() -> dict[str, Any]:
    if not settings.agent_enable_thinking:
        return {}
    payload: dict[str, Any] = {"enable_thinking": True}
    if settings.agent_thinking_budget is not None:
        payload["thinking_budget"] = settings.agent_thinking_budget
    return payload


def _log_stream_chunk(
    *,
    answer_delta: str,
    reasoning_delta: str,
    tool_call_chunks: int,
    chunk_position: str | None,
) -> None:
    if not settings.agent_stream_diagnostics:
        return
    if not chunk_position and not tool_call_chunks and not reasoning_delta:
        return
    logger.debug(
        "dashscope stream chunk",
        answer_delta_len=len(answer_delta),
        reasoning_delta_len=len(reasoning_delta),
        tool_call_chunks=tool_call_chunks,
        chunk_position=chunk_position,
        has_answer_delta=bool(answer_delta),
        has_reasoning_delta=bool(reasoning_delta),
    )
