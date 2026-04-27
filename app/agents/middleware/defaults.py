"""Default middleware stack for the native-only create_agent runtime."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware, HumanInTheLoopMiddleware
from langchain.agents.middleware.human_in_the_loop import InterruptOnConfig
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.types import Command

from app.agents.runtime.constants import REQUEST_HUMAN_INPUT_TOOL_NAME
from app.tools.result_protocol import parse_tool_result_payload

BASE_SYSTEM_PROMPT = """
你是创新创业知识问答助手。

运行原则：
- 先判断当前问题是否属于创新创业、课程资料、项目材料或确定性数值计算相关范围。
- 如果是闲聊或明显超出创新创业领域的问题，直接礼貌引导用户改问创新创业相关问题，不要展开闲聊。
- 创新创业相关问题默认优先考虑 `knowledge_retrieval`，尤其是涉及私有知识库、课程资料、项目材料或上下文证据时。
- `web_search` 只用于最新、实时、外部信息，或知识库未命中后仍需要外部信息时。
- `math_calculator` 只用于确定性数值计算。
- 如果缺少关键对象、引用对象或上下文，使用 `request_human_input` 进入人类参与流程，而不是猜测。
- 当你决定直接回答、调用工具或请求澄清时，优先在 reasoning 中给出与当前问题直接相关的具体依据。
- 不要输出“分析问题意图”“评估工具与知识来源”“开始直接回答”这类固定阶段口号。
- 以上要求只影响 reasoning 的表达质量，不改变 `knowledge_retrieval` / `web_search` /
  `math_calculator` / `request_human_input` 的既有路由原则。
- 输出中文，准确、简洁、对用户直接有用。
""".strip()


@dataclass(slots=True)
class NativeAgentContext:
    request_id: str
    conversation_id: str
    user_id: str
    memory_summary: str | None = None


class PromptContextMiddleware(AgentMiddleware[Any, NativeAgentContext, Any]):
    """Inject only the minimal dynamic system prompt context."""

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        system_message = SystemMessage(
            content="\n\n".join(
                part
                for part in (
                    BASE_SYSTEM_PROMPT,
                    _memory_block(request.runtime.context.memory_summary),
                )
                if part
            )
        )
        return await handler(request.override(system_message=system_message))


class ToolResultNormalizationMiddleware(AgentMiddleware[Any, NativeAgentContext, Any]):
    """Normalize tool results and surface tool failures as proper ToolMessages."""

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        result = await handler(request)
        if isinstance(result, Command):
            return result
        if isinstance(result, ToolMessage):
            if result.name == REQUEST_HUMAN_INPUT_TOOL_NAME:
                return result
            payload = parse_tool_result_payload(result.content)
            if payload is None:
                return result
            return ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id=result.tool_call_id,
                name=result.name or str(payload.get("tool") or request.tool_call.get("name") or "unknown"),
                artifact=payload,
                status="error" if not bool(payload.get("success", True)) else "success",
            )
        return result


def build_default_middleware() -> Sequence[AgentMiddleware[Any, NativeAgentContext, Any]]:
    hitl = HumanInTheLoopMiddleware(
        interrupt_on={
            REQUEST_HUMAN_INPUT_TOOL_NAME: InterruptOnConfig(
                allowed_decisions=["edit", "reject"],
                description=cast(Any, _human_input_description),
            )
        }
    )
    return cast(
        Sequence[AgentMiddleware[Any, NativeAgentContext, Any]],
        (
            PromptContextMiddleware(),
            hitl,
            ToolResultNormalizationMiddleware(),
        ),
    )


def _human_input_description(tool_call: dict[str, Any], _state: dict[str, Any], _runtime: Any) -> str:
    prompt = str((tool_call.get("args") or {}).get("prompt") or "请提供下一步所需的人类输入。")
    return prompt


def _memory_block(summary: str | None) -> str:
    text = str(summary or "").strip()
    if not text:
        return ""
    return f"【Conversation memory】\n{text}"
