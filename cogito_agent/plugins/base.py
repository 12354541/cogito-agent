from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from cogito_agent.tools.base import ToolResult


@dataclass(slots=True)
class ToolPolicyDecision:
    allow: bool = True
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PhaseModule(Protocol):
    name: str

    async def on_phase(self, phase: str, **kwargs: Any) -> None:
        ...


class ToolInterceptor(Protocol):
    name: str

    async def on_tool_pre(self, tool_name: str, arguments: dict[str, Any], **kwargs: Any) -> ToolPolicyDecision:
        ...

    async def on_tool_result(self, tool_name: str, arguments: dict[str, Any], result: ToolResult, **kwargs: Any) -> ToolResult:
        ...


class BasePlugin:
    name = "base"

    async def on_phase(self, phase: str, **kwargs: Any) -> None:
        return None

    async def on_tool_pre(self, tool_name: str, arguments: dict[str, Any], **kwargs: Any) -> ToolPolicyDecision:
        return ToolPolicyDecision()

    async def on_tool_result(self, tool_name: str, arguments: dict[str, Any], result: ToolResult, **kwargs: Any) -> ToolResult:
        return result
