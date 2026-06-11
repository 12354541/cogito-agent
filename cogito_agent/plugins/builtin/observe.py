from __future__ import annotations

from typing import Any

from cogito_agent.plugins.base import BasePlugin
from cogito_agent.tools.base import ToolResult


class ObservePlugin(BasePlugin):
    name = "observe"

    async def on_phase(self, phase: str, **kwargs: Any) -> None:
        trace = kwargs.get("trace")
        tracer = kwargs.get("tracer")
        if trace and tracer:
            tracer.record_event(trace, event="plugin_phase", metadata={"plugin": self.name, "phase": phase})

    async def on_tool_result(self, tool_name: str, arguments: dict[str, Any], result: ToolResult, **kwargs: Any) -> ToolResult:
        trace = kwargs.get("trace")
        tracer = kwargs.get("tracer")
        if trace and tracer:
            tracer.record_event(
                trace,
                event="plugin_tool_observed",
                metadata={"plugin": self.name, "tool_name": tool_name, "success": result.success},
            )
        return result
