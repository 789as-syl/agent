from __future__ import annotations

from typing import Any, cast

from app.agents.middleware.defaults import BASE_SYSTEM_PROMPT
from app.agents.native_agent_runner import _classify_query_intent
from app.tools.math_tool import create_math_tool
from app.tools.retrieval_tool import create_retrieval_tool
from app.tools.web_search_tool import create_web_search_tool


class _FakeSession:
    is_active = False

    async def rollback(self) -> None:
        return None


def test_base_system_prompt_reflects_three_tool_policy() -> None:
    assert "闲聊或明显超出创新创业领域的问题" in BASE_SYSTEM_PROMPT
    assert "`knowledge_retrieval`" in BASE_SYSTEM_PROMPT
    assert "`web_search`" in BASE_SYSTEM_PROMPT
    assert "`math_calculator`" in BASE_SYSTEM_PROMPT
    assert "`request_human_input`" in BASE_SYSTEM_PROMPT


def test_query_intent_allows_domain_context_and_math_queries() -> None:
    assert _classify_query_intent("什么是商业模式画布？")["short_circuit"] is False
    assert _classify_query_intent("老师在课上怎么定义MVP？")["short_circuit"] is False
    assert _classify_query_intent("根据我上传的课程讲义总结本项目的融资风险")["short_circuit"] is False
    assert _classify_query_intent("讲解 app 下 agent 逻辑")["short_circuit"] is False
    assert _classify_query_intent("2 + 2 * 5")["short_circuit"] is False
    assert _classify_query_intent("帮我计算毛利率")["short_circuit"] is False


def test_query_intent_short_circuits_casual_and_out_of_scope_queries() -> None:
    casual = _classify_query_intent("你好呀，陪我聊聊天")
    out_of_scope = _classify_query_intent("法国的首都是什么？")

    assert casual["short_circuit"] is True
    assert casual["reason"] == "casual_chat"
    assert "不提供闲聊服务" in str(casual["message"])

    assert out_of_scope["short_circuit"] is False
    assert out_of_scope["reason"] == "fact_lookup"
    assert str(out_of_scope["message"]) == ""


def test_query_intent_prefers_domain_signal_over_greeting_noise() -> None:
    mixed = _classify_query_intent("你好，什么是商业模式画布？")

    assert mixed["short_circuit"] is False
    assert mixed["reason"] == "domain"


def test_remaining_tool_descriptions_match_three_tool_policy() -> None:
    retrieval_tool = create_retrieval_tool(cast(Any, _FakeSession()))
    math_tool = create_math_tool()
    web_tool = create_web_search_tool()

    assert "default first tool for in-scope domain questions" in retrieval_tool.description
    assert "deterministic math evaluation" in math_tool.description
    assert "timely external information outside the knowledge base" in web_tool.description
