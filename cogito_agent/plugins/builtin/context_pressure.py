from __future__ import annotations

from typing import Any

from cogito_agent.plugins.base import BasePlugin
from cogito_agent.tracing.context import TraceContext


def _estimate_tokens(text: str) -> int:
    return len(text) // 2 + 1


def _estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        for value in msg.values():
            if isinstance(value, str):
                total += _estimate_tokens(value)
    return total


class ContextPressurePlugin(BasePlugin):
    name = "context_pressure"

    def __init__(
        self,
        max_prompt_tokens: int = 24000,
        pressure_ratio: float = 0.8,
        min_history_messages: int = 2,
    ) -> None:
        self.max_prompt_tokens = max_prompt_tokens
        self.pressure_ratio = pressure_ratio
        self.min_history_messages = min_history_messages

    async def on_phase(self, phase: str, **kwargs: Any) -> None:
        pass

    async def on_tool_pre(self, tool_name: str, arguments: dict[str, Any], **kwargs: Any) -> Any:
        from cogito_agent.plugins.base import ToolPolicyDecision
        return ToolPolicyDecision()

    def check_pressure(
        self,
        messages: list[dict[str, Any]],
        trace: TraceContext | None = None,
        tracer: Any = None,
    ) -> dict[str, Any]:
        estimated = _estimate_messages_tokens(messages)
        threshold = int(self.max_prompt_tokens * self.pressure_ratio)
        result: dict[str, Any] = {
            "estimated_tokens": estimated,
            "threshold": threshold,
            "max_prompt_tokens": self.max_prompt_tokens,
            "over_threshold": estimated > threshold,
            "action": "none",
        }
        if estimated <= threshold:
            return result

        compressed = False
        if len(messages) > self.min_history_messages + 1:
            kept = messages[:1] + messages[-(self.min_history_messages + 1) :]
            kept_tokens = _estimate_messages_tokens(kept)
            if kept_tokens < threshold:
                messages[:] = kept
                compressed = True
                result["action"] = "trimmed_history"

        if not compressed:
            for msg in messages:
                if isinstance(msg.get("content"), str) and len(msg["content"]) > 1000:
                    msg["content"] = msg["content"][:1000] + f"... (truncated, original len={len(msg['content'])})"
            compressed = True
            result["action"] = "truncated_content"

        if tracer and trace:
            tracer.record_event(
                trace,
                event="context_pressure_applied",
                metadata=result,
            )
        result["estimated_tokens"] = _estimate_messages_tokens(messages)
        return result
