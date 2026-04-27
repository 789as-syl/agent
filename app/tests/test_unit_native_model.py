from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import tool

from app.agents.runtime.native_model import (
    REQUEST_HUMAN_INPUT_TOOL_NAME,
    DashScopeAgentChatModel,
    langchain_messages_to_dashscope,
    message_content_to_blocks,
    message_content_to_text,
    parse_dashscope_response_to_ai_message,
)
from app.tools.retrieval_tool import create_retrieval_tool


def test_langchain_messages_to_dashscope_converts_tool_and_ai_calls() -> None:
    messages = [
        HumanMessage(content="hello"),
        AIMessage(
            content=[{"type": "text", "text": "structured hello"}],
            tool_calls=[{"id": "call-1", "name": "lookup", "args": {"query": "python"}}],
        ),
        ToolMessage(content='{"success": true}', tool_call_id="call-1", name="lookup"),
    ]

    payload = langchain_messages_to_dashscope(messages)

    assert payload[0]["role"] == "user"
    assert payload[1]["role"] == "assistant"
    assert payload[1]["content"] == "structured hello"
    assert payload[1]["tool_calls"][0]["function"]["name"] == "lookup"
    assert payload[2]["role"] == "tool"
    assert payload[2]["tool_call_id"] == "call-1"


def test_parse_dashscope_response_to_ai_message_preserves_content_blocks() -> None:
    response = SimpleNamespace(
        status_code=200,
        output=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=[{"type": "text", "text": "hello"}],
                        tool_calls=[
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"query":"python"}',
                                },
                            }
                        ],
                    )
                )
            ]
        ),
    )

    message = parse_dashscope_response_to_ai_message(response)

    assert isinstance(message, AIMessage)
    assert message_content_to_text(message.content) == "hello"
    assert message_content_to_blocks(message.content) == [{"type": "text", "text": "hello"}]
    assert message.tool_calls[0]["name"] == "lookup"


def test_dashscope_agent_chat_model_bind_tools_returns_bound_clone() -> None:
    @tool
    def hello(name: str) -> str:
        """Say hello."""
        return f"hello {name}"

    model = DashScopeAgentChatModel(model_name="qwen-turbo")
    bound = model.bind_tools([hello])

    assert bound is not model
    assert len(bound.bound_tools) == 1
    assert bound.bound_tools[0]["function"]["name"] == "hello"


async def test_dashscope_agent_chat_model_works_with_create_agent_tool_loop() -> None:
    @tool
    def hello(name: str) -> str:
        """Say hello."""
        return f"hello {name}"

    model = DashScopeAgentChatModel(model_name="qwen-turbo")

    responses = [
        SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                {
                                    "id": "call-1",
                                    "function": {"name": "hello", "arguments": '{"name":"bob"}'},
                                }
                            ],
                        )
                    )
                ]
            ),
        ),
        SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=[{"type": "text", "text": "done"}], tool_calls=[]))]
            ),
        ),
    ]

    with patch("app.agents.runtime.native_model.Generation.call", side_effect=lambda **_: responses.pop(0)):
        agent = create_agent(model=model, tools=[hello])
        chunks = []
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": "hi"}]},
            stream_mode="values",
        ):
            chunks.append(chunk)

    assert message_content_to_text(chunks[-1]["messages"][-1].content) == "done"
    assert isinstance(chunks[-1]["messages"][-2], ToolMessage)


def test_request_human_input_constant_is_stable() -> None:
    assert REQUEST_HUMAN_INPUT_TOOL_NAME == "request_human_input"


def test_dashscope_agent_chat_model_stream_emits_incremental_answer_and_reasoning() -> None:
    model = DashScopeAgentChatModel(model_name="qwen-turbo")
    responses = [
        SimpleNamespace(
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason=None,
                        message=SimpleNamespace(content="创", reasoning_content="正在分析"),
                    )
                ]
            )
        ),
        SimpleNamespace(
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content="创新", reasoning_content="正在分析问题"),
                    )
                ]
            )
        ),
    ]

    with patch("app.agents.runtime.native_model.Generation.call", return_value=iter(responses)):
        chunks = list(model._stream([HumanMessage(content="hi")]))

    assert len(chunks) == 2
    assert isinstance(chunks[0], ChatGenerationChunk)
    assert chunks[0].message.content == "创"
    assert chunks[0].message.additional_kwargs["reasoning_delta"] == "正在分析"
    assert chunks[1].message.content == "新"
    assert chunks[1].message.additional_kwargs["reasoning_delta"] == "问题"


async def test_create_agent_toolruntime_injection_works_for_retrieval_tool() -> None:
    class FakeSession:
        is_active = False

        async def rollback(self) -> None:
            return None

    model = DashScopeAgentChatModel(model_name="qwen-turbo")
    tool = create_retrieval_tool(FakeSession())
    responses = [
        SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "knowledge_retrieval",
                                        "arguments": '{"query":"创新创业机会识别"}',
                                    },
                                }
                            ],
                        )
                    )
                ]
            ),
        ),
        SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))]
            ),
        ),
    ]

    fake_result = SimpleNamespace(knowledge_points=[], explanation=None)

    with (
        patch("app.agents.runtime.native_model.Generation.call", side_effect=lambda **_: responses.pop(0)),
        patch("app.tools.retrieval_tool.RetrievalService.retrieve", new=AsyncMock(return_value=fake_result)),
    ):
        agent = create_agent(model=model, tools=[tool])
        chunks = []
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": "hi"}]},
            stream_mode="values",
        ):
            chunks.append(chunk)

    assert message_content_to_text(chunks[-1]["messages"][-1].content) == "done"
    assert isinstance(chunks[-1]["messages"][-2], ToolMessage)
