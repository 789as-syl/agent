"""Factory for the native-only create_agent runtime."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.middleware.defaults import NativeAgentContext, build_default_middleware
from app.agents.runtime.constants import REQUEST_HUMAN_INPUT_TOOL_NAME
from app.agents.runtime.native_checkpoint import get_native_checkpointer
from app.agents.runtime.native_model import DashScopeAgentChatModel
from app.core.config import settings
from app.tools.registry import build_default_tool_registry


def create_request_human_input_tool() -> Any:
    @tool(
        REQUEST_HUMAN_INPUT_TOOL_NAME,
        description=(
            "Use when the user question is missing a critical object, reference, or context and you need explicit "
            "human input before continuing. Provide a clear prompt. The human response is supplied by the HITL layer."
        ),
    )
    def request_human_input(prompt: str, response: str = "") -> str:
        return response

    return request_human_input


async def create_native_agent_graph(db_session: AsyncSession) -> Any:
    registry = build_default_tool_registry(db_session)
    tools = registry.list_tools()
    tools.append(create_request_human_input_tool())
    model = DashScopeAgentChatModel(
        model_name=settings.agent_generation_model,
        temperature=settings.agent_generation_temperature,
        max_tokens=settings.agent_generation_max_tokens,
    )
    checkpointer = await get_native_checkpointer()
    agent = create_agent(
        model=model,
        tools=tools,
        middleware=build_default_middleware(),
        context_schema=NativeAgentContext,
        checkpointer=checkpointer,
        name="knowledge_base_native_agent",
    )
    return agent


__all__ = [
    "NativeAgentContext",
    "create_native_agent_graph",
    "create_request_human_input_tool",
]
