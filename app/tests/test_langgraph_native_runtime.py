from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.runtime.constants import REQUEST_HUMAN_INPUT_TOOL_NAME
from app.agents.runtime.native_model import DashScopeAgentChatModel, message_content_to_text


def _fake_response(*, content=None, tool_calls: list[dict] | None = None):
    return SimpleNamespace(
        status_code=200,
        output=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content or "", tool_calls=tool_calls or []))]
        ),
    )


async def test_create_agent_hitl_interrupt_and_resume_with_checkpointer() -> None:
    @tool(REQUEST_HUMAN_INPUT_TOOL_NAME)
    def request_human_input(prompt: str, response: str = "") -> str:
        """Internal HITL response tool."""
        return response

    saver = InMemorySaver()
    model = DashScopeAgentChatModel(model_name="qwen-turbo")
    responses = [
        _fake_response(
            tool_calls=[
                {
                    "id": "call-1",
                    "function": {
                        "name": REQUEST_HUMAN_INPUT_TOOL_NAME,
                        "arguments": '{"prompt":"which file?","response":""}',
                    },
                }
            ]
        ),
        _fake_response(content=[{"type": "text", "text": "thanks, I have enough context now"}]),
    ]
    agent = create_agent(
        model=model,
        tools=[request_human_input],
        checkpointer=saver,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={REQUEST_HUMAN_INPUT_TOOL_NAME: {"allowed_decisions": ["edit", "reject"]}}
            )
        ],
    )
    config = {"configurable": {"thread_id": "runtime-test-thread"}}

    with patch("app.agents.runtime.native_model.Generation.call", side_effect=lambda **_: responses.pop(0)):
        first_chunks = []
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": "fix it"}]},
            config=config,
            stream_mode="values",
        ):
            first_chunks.append(chunk)

        interrupt_chunk = first_chunks[-1]
        assert "__interrupt__" in interrupt_chunk
        hitl_request = interrupt_chunk["__interrupt__"][0].value
        assert hitl_request["action_requests"][0]["name"] == REQUEST_HUMAN_INPUT_TOOL_NAME
        assert hitl_request["review_configs"][0]["allowed_decisions"] == ["edit", "reject"]

        resumed_chunks = []
        async for chunk in agent.astream(
            Command(
                resume={
                    "decisions": [
                        {
                            "type": "edit",
                            "edited_action": {
                                "name": REQUEST_HUMAN_INPUT_TOOL_NAME,
                                "args": {"prompt": "which file?", "response": "app/api/chat_runs.py"},
                            },
                        }
                    ]
                }
            ),
            config=config,
            stream_mode="values",
        ):
            resumed_chunks.append(chunk)

    assert message_content_to_text(resumed_chunks[-1]["messages"][-1].content) == "thanks, I have enough context now"
