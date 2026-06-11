from __future__ import annotations

from typing import Any

from cogito_agent.plugins.base import BasePlugin, ToolPolicyDecision
from cogito_agent.plugins.event_bus import EventBus
from cogito_agent.tools.base import ToolResult


class PluginManager:
    def __init__(self, plugins: list[BasePlugin] | None = None, event_bus: EventBus | None = None) -> None:
        self.plugins: list[BasePlugin] = plugins or []
        self.event_bus = event_bus or EventBus()

    def register(self, plugin: BasePlugin) -> None:
        self.plugins.append(plugin)

    def list_plugins(self) -> list[dict[str, Any]]:
        return [{"name": plugin.name, "class": plugin.__class__.__name__} for plugin in self.plugins]

    async def run_phase(self, phase: str, **kwargs: Any) -> None:
        await self.event_bus.publish(f"phase:{phase}", kwargs)
        for plugin in self.plugins:
            await plugin.on_phase(phase, **kwargs)

    async def check_tool_pre(self, tool_name: str, arguments: dict[str, Any], **kwargs: Any) -> ToolPolicyDecision:
        for plugin in self.plugins:
            decision = await plugin.on_tool_pre(tool_name, arguments, **kwargs)
            if not decision.allow:
                return decision
        return ToolPolicyDecision()

    async def apply_tool_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        **kwargs: Any,
    ) -> ToolResult:
        current = result
        for plugin in self.plugins:
            current = await plugin.on_tool_result(tool_name, arguments, current, **kwargs)
        return current
