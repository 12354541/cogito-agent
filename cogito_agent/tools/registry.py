from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from cogito_agent.plugins.manager import PluginManager
from cogito_agent.tools.base import RiskLevel, Tool, ToolResult
from cogito_agent.tracing.context import TraceContext

if TYPE_CHECKING:
    from cogito_agent.tracing.tracer import Tracer


class ToolRegistry:
    def __init__(
        self,
        *,
        allowed_risk_levels: set[RiskLevel] | None = None,
        plugin_manager: PluginManager | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self.allowed_risk_levels = allowed_risk_levels or {"read-only", "write", "network"}
        self.plugin_manager = plugin_manager or PluginManager()

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self._tools.values() if tool.enabled]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        trace: TraceContext | None = None,
        tracer: Tracer | None = None,
    ) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(content="", success=False, error=f"Unknown tool: {name}")
        if not tool.enabled:
            return ToolResult(content="", success=False, error=f"Tool disabled: {name}")
        if tool.risk_level not in self.allowed_risk_levels:
            return ToolResult(content="", success=False, error=f"Tool risk level not allowed: {tool.risk_level}")

        validation_error = self._validate_arguments(tool, arguments)
        if validation_error:
            return ToolResult(content="", success=False, error=validation_error)

        decision = await self.plugin_manager.check_tool_pre(
            name,
            arguments,
            trace=trace,
            tracer=tracer,
            tool=tool,
        )
        if not decision.allow:
            return ToolResult(content="", success=False, error=decision.reason or "Tool blocked by plugin.", metadata=decision.metadata)

        span = None
        started = time.perf_counter()
        if trace and tracer:
            span = tracer.start_span(
                trace,
                span_type="tool",
                name=name,
                input_preview={"arguments": arguments, "risk_level": tool.risk_level},
            )
            tracer.record_event(trace, event="tool_call_started", metadata={"tool_name": name})
        try:
            result = await tool.execute(**arguments)
        except Exception as exc:
            result = ToolResult(content="", success=False, error=str(exc))

        duration_ms = int((time.perf_counter() - started) * 1000)
        result.metadata.setdefault("duration_ms", duration_ms)
        result = await self.plugin_manager.apply_tool_result(
            name,
            arguments,
            result,
            trace=trace,
            tracer=tracer,
            tool=tool,
        )
        if trace and tracer:
            tracer.record_event(
                trace,
                event="tool_call_finished",
                metadata={
                    "tool_name": name,
                    "success": result.success,
                    "duration_ms": duration_ms,
                    "error": result.error,
                },
            )
            if span:
                tracer.end_span(
                    trace,
                    span,
                    status="ok" if result.success else "error",
                    output_preview={"content": result.content[:200], "error": result.error},
                    error=result.error,
                )
        return result

    @staticmethod
    def _validate_arguments(tool: Tool, arguments: dict[str, Any]) -> str | None:
        required = tool.parameters.get("required", [])
        for key in required:
            if key not in arguments:
                return f"Missing required argument: {key}"
        properties = tool.parameters.get("properties", {})
        for key in arguments:
            if key not in properties:
                return f"Unknown argument: {key}"
        return None
