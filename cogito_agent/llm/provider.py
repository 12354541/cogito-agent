from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from cogito_agent.llm.types import LLMResponse
from cogito_agent.tracing.context import TraceContext


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        stream: bool = False,
        trace: TraceContext | None = None,
    ) -> LLMResponse:
        raise NotImplementedError
