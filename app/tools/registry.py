"""Runtime tool registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.tools.catalog import ToolSpec, get_tool_spec, iter_enabled_tool_specs


@dataclass(slots=True)
class RegisteredTool:
    spec: ToolSpec
    tool: Any

    @property
    def name(self) -> str:
        return self.spec.name


class ToolRegistry:
    """Runtime registry that manages LangChain-compatible tools by name."""

    def __init__(self, tools: Iterable[Any] | None = None):
        self._tools: dict[str, RegisteredTool] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(
        self,
        tool: Any,
        *,
        spec: ToolSpec | None = None,
    ) -> None:
        tool_name = getattr(tool, "name", None)
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("Tool must expose a non-empty string `name` attribute")
        resolved_spec = spec or get_tool_spec(tool_name) or ToolSpec(
            name=tool_name,
            factory=lambda _session: tool,
            display_name=tool_name,
            kind="custom",
            evidence_source="none",
            cost_level="low",
        )
        self._tools[tool_name] = RegisteredTool(
            spec=resolved_spec,
            tool=tool,
        )

    def get(self, name: str) -> Any | None:
        entry = self._tools.get(name)
        return entry.tool if entry else None

    def get_spec(self, name: str) -> ToolSpec | None:
        entry = self._tools.get(name)
        return entry.spec if entry else None

    def list_tools(self, tool_names: Iterable[str] | None = None) -> list[Any]:
        allowed = set(tool_names) if tool_names else None
        return [
            entry.tool
            for entry in self._tools.values()
            if allowed is None or entry.name in allowed
        ]

    def list_tool_names(self, tool_names: Iterable[str] | None = None) -> list[str]:
        if not tool_names:
            return list(self._tools.keys())
        allowed = set(tool_names)
        return [name for name in self._tools if name in allowed]

    def list_specs(self, tool_names: Iterable[str] | None = None) -> list[ToolSpec]:
        allowed = set(tool_names) if tool_names else None
        return [
            entry.spec
            for entry in self._tools.values()
            if allowed is None or entry.name in allowed
        ]

    def describe_tools(self, tool_names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        allowed = set(tool_names) if tool_names else None
        return [
            {
                "name": entry.name,
                "display_name": entry.spec.display_name,
                "description": getattr(entry.tool, "description", "") or "",
                "input_schema": _tool_args_schema(entry.tool),
                "kind": entry.spec.kind,
                "evidence_source": entry.spec.evidence_source,
                "cost_level": entry.spec.cost_level,
            }
            for entry in self._tools.values()
            if allowed is None or entry.name in allowed
        ]


def _tool_args_schema(tool: Any) -> dict[str, Any]:
    args = getattr(tool, "args", {})
    return args if isinstance(args, dict) else {}


def _parse_enabled_tool_names(raw: str) -> set[str] | None:
    parsed = {item.strip() for item in raw.split(",") if item and item.strip()}
    return parsed or None


def build_default_tool_registry(db_session: AsyncSession) -> ToolRegistry:
    """Build default agent tool set for current runtime."""
    registry = ToolRegistry()
    enabled = _parse_enabled_tool_names(settings.agent_enabled_tools)
    # Tool enablement stays config-driven so runtime capability selection does
    # not drift into call sites.
    for spec in iter_enabled_tool_specs(enabled):
        registry.register(spec.factory(db_session), spec=spec)

    if not registry.list_tool_names():
        raise ValueError(
            "No agent tools enabled. Check AGENT_ENABLED_TOOLS / agent_enabled_tools setting."
        )
    return registry
