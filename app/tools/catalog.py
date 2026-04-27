"""Agent tool catalog and metadata registry."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.math_tool import create_math_tool
from app.tools.retrieval_tool import create_retrieval_tool
from app.tools.web_search_tool import create_web_search_tool


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    factory: Callable[[AsyncSession], Any]
    display_name: str
    kind: str
    evidence_source: str
    cost_level: str
    requires_private_context: bool = False
    requires_freshness: bool = False


def _build_retrieval_tool(db_session: AsyncSession) -> Any:
    return create_retrieval_tool(db_session)


def _build_math_tool(_: AsyncSession) -> Any:
    return create_math_tool()


def _build_web_search_tool(_: AsyncSession) -> Any:
    return create_web_search_tool()


DEFAULT_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="knowledge_retrieval",
        factory=_build_retrieval_tool,
        display_name="检索知识库",
        kind="retrieval",
        evidence_source="kb",
        cost_level="medium",
        requires_private_context=True,
    ),
    ToolSpec(
        name="math_calculator",
        factory=_build_math_tool,
        display_name="计算公式",
        kind="math",
        evidence_source="none",
        cost_level="low",
    ),
    ToolSpec(
        name="web_search",
        factory=_build_web_search_tool,
        display_name="网页搜索",
        kind="web",
        evidence_source="web",
        cost_level="medium",
        requires_freshness=True,
    ),
)

DEFAULT_ENABLED_TOOL_NAMES = frozenset({"knowledge_retrieval", "math_calculator"})


def iter_enabled_tool_specs(enabled_names: set[str] | None = None) -> Iterable[ToolSpec]:
    enabled = enabled_names if enabled_names is not None else DEFAULT_ENABLED_TOOL_NAMES
    for spec in DEFAULT_TOOL_SPECS:
        if spec.name not in enabled:
            continue
        yield spec


def get_tool_spec(name: str) -> ToolSpec | None:
    for spec in DEFAULT_TOOL_SPECS:
        if spec.name == name:
            return spec
    return None
