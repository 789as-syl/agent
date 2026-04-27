"""Unit tests for the tool registry."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.tools.catalog import DEFAULT_TOOL_SPECS, iter_enabled_tool_specs
from app.tools.registry import build_default_tool_registry

EXPECTED_DEFAULT_TOOL_NAMES = ["knowledge_retrieval", "math_calculator"]
EXPECTED_BUSINESS_TOOL_NAMES = ["knowledge_retrieval", "math_calculator", "web_search"]


def test_iter_enabled_tool_specs_returns_safe_default_tools():
    specs = list(iter_enabled_tool_specs())

    assert [spec.name for spec in specs] == EXPECTED_DEFAULT_TOOL_NAMES
    assert "request_human_input" not in [spec.name for spec in specs]
    assert "web_search" not in [spec.name for spec in specs]
    assert [spec.name for spec in DEFAULT_TOOL_SPECS] == EXPECTED_BUSINESS_TOOL_NAMES


def test_iter_enabled_tool_specs_filters_by_enabled_names():
    specs = list(iter_enabled_tool_specs({"knowledge_retrieval", "web_search"}))

    assert [spec.name for spec in specs] == ["knowledge_retrieval", "web_search"]


@pytest.mark.asyncio
async def test_tool_registry_describe_tools_can_filter_by_name(db_session):
    registry = build_default_tool_registry(db_session)

    descriptions = registry.describe_tools(tool_names={"knowledge_retrieval", "math_calculator", "web_search"})

    assert [item["name"] for item in descriptions] == ["knowledge_retrieval", "math_calculator"]


@pytest.mark.asyncio
async def test_build_default_tool_registry_respects_enabled_tools(db_session):
    old_value = settings.agent_enabled_tools
    settings.agent_enabled_tools = "knowledge_retrieval,web_search"
    try:
        registry = build_default_tool_registry(db_session)
    finally:
        settings.agent_enabled_tools = old_value

    assert registry.list_tool_names() == ["knowledge_retrieval", "web_search"]
    descriptions = registry.describe_tools()
    assert [item["name"] for item in descriptions] == ["knowledge_retrieval", "web_search"]
    assert descriptions[0]["kind"] == "retrieval"
    assert descriptions[1]["kind"] == "web"


@pytest.mark.asyncio
async def test_build_default_tool_registry_raises_when_none_enabled(db_session):
    old_value = settings.agent_enabled_tools
    settings.agent_enabled_tools = "unknown_tool"
    try:
        with pytest.raises(ValueError, match="No agent tools enabled"):
            build_default_tool_registry(db_session)
    finally:
        settings.agent_enabled_tools = old_value
