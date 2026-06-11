from __future__ import annotations

from typing import Any

from cogito_agent.plugins.base import BasePlugin, ToolPolicyDecision


class ShellSafetyPlugin(BasePlugin):
    name = "shell_safety"

    async def on_tool_pre(self, tool_name: str, arguments: dict[str, Any], **kwargs: Any) -> ToolPolicyDecision:
        tool = kwargs.get("tool")
        if getattr(tool, "risk_level", None) == "shell":
            return ToolPolicyDecision(False, "Shell tools are disabled by default.")
        return ToolPolicyDecision()
