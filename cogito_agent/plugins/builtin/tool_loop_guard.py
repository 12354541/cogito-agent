from __future__ import annotations

from collections import defaultdict
from typing import Any

from cogito_agent.plugins.base import BasePlugin, ToolPolicyDecision


class ToolLoopGuardPlugin(BasePlugin):
    name = "tool_loop_guard"

    def __init__(self, max_same_call: int = 2, max_total_calls: int = 30) -> None:
        self.max_same_call = max_same_call
        self.max_total_calls = max_total_calls
        self._same_call_counts: dict[str, int] = defaultdict(int)
        self._total_calls = 0

    async def on_phase(self, phase: str, **kwargs: Any) -> None:
        if phase == "before_turn":
            self._same_call_counts.clear()
            self._total_calls = 0

    async def on_tool_pre(self, tool_name: str, arguments: dict[str, Any], **kwargs: Any) -> ToolPolicyDecision:
        self._total_calls += 1
        if self._total_calls > self.max_total_calls:
            return ToolPolicyDecision(False, "Tool loop guard blocked total tool call limit.")
        key = f"{tool_name}:{repr(sorted(arguments.items()))}"
        self._same_call_counts[key] += 1
        if self._same_call_counts[key] > self.max_same_call:
            return ToolPolicyDecision(False, f"Tool loop guard blocked repeated call to {tool_name}.")
        return ToolPolicyDecision()
