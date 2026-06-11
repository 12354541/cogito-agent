from __future__ import annotations

from typing import Any

from cogito_agent.llm.provider import LLMProvider
from cogito_agent.llm.types import LLMResponse
from cogito_agent.tracing.context import TraceContext


class MockLLMProvider(LLMProvider):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        stream: bool = False,
        trace: TraceContext | None = None,
    ) -> LLMResponse:
        if not self.responses:
            return LLMResponse(content="")
        return self.responses.pop(0)
