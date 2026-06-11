from __future__ import annotations

import asyncio

from cogito_agent.agent.reasoner import LLMReasoner
from cogito_agent.llm.provider import LLMProvider
from cogito_agent.llm.types import LLMResponse, LLMToolCall
from cogito_agent.prompting.manager import PromptManager
from cogito_agent.tools.calculator import CalculatorTool
from cogito_agent.tools.registry import ToolRegistry
from cogito_agent.tracing.tracer import Tracer


class MockLLMProvider(LLMProvider):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses

    async def chat(self, *args, **kwargs) -> LLMResponse:  # noqa: ANN002, ANN003
        return self.responses.pop(0)


def test_llm_reasoner_executes_tool_loop(tmp_path):
    provider = MockLLMProvider(
        [
            LLMResponse(tool_calls=[LLMToolCall(id="call_1", name="calculator", arguments={"expression": "2+3*4"})]),
            LLMResponse(content="结果是 14。", metadata={"model": "mock"}),
        ]
    )
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    tracer = Tracer(workspace=tmp_path)
    trace = tracer.start_trace(session_id="default", user_message_preview="计算 2+3*4")
    reasoner = LLMReasoner(
        llm_provider=provider,
        prompt_manager=PromptManager(),
        tool_registry=registry,
        max_iterations=4,
    )

    result = asyncio.run(reasoner.run(history=[], user_content="计算 2+3*4", trace=trace, tracer=tracer))

    assert result.content == "结果是 14。"
    assert result.tool_calls[0]["name"] == "calculator"
    assert result.tool_calls[0]["success"] is True
