from __future__ import annotations

import asyncio

from cogito_agent.agent.reasoner import LLMReasoner
from cogito_agent.llm.provider import LLMProvider
from cogito_agent.llm.types import LLMResponse, LLMToolCall
from cogito_agent.plugins.builtin.context_pressure import ContextPressurePlugin
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


def test_llm_reasoner_handles_malformed_tool_call(tmp_path):
    provider = MockLLMProvider(
        [
            LLMResponse(tool_calls=[LLMToolCall(id="call_1", name="", arguments={})]),
            LLMResponse(content="完成。", metadata={"model": "mock"}),
        ]
    )
    registry = ToolRegistry()
    tracer = Tracer(workspace=tmp_path)
    trace = tracer.start_trace(session_id="default", user_message_preview="test malformed")
    reasoner = LLMReasoner(
        llm_provider=provider,
        prompt_manager=PromptManager(),
        tool_registry=registry,
        max_iterations=4,
    )

    result = asyncio.run(reasoner.run(history=[], user_content="test", trace=trace, tracer=tracer))

    assert "完成" in result.content
    assert any(not c["success"] for c in result.tool_calls)


def test_llm_reasoner_max_iterations_reached(tmp_path):
    provider = MockLLMProvider(
        [
            LLMResponse(tool_calls=[LLMToolCall(id="c1", name="calculator", arguments={"expression": "1+1"})]),
            LLMResponse(tool_calls=[LLMToolCall(id="c2", name="calculator", arguments={"expression": "2+2"})]),
            LLMResponse(tool_calls=[LLMToolCall(id="c3", name="calculator", arguments={"expression": "3+3"})]),
        ]
    )
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    tracer = Tracer(workspace=tmp_path)
    trace = tracer.start_trace(session_id="default", user_message_preview="test max iter")
    reasoner = LLMReasoner(
        llm_provider=provider,
        prompt_manager=PromptManager(),
        tool_registry=registry,
        max_iterations=2,
    )

    result = asyncio.run(reasoner.run(history=[], user_content="test", trace=trace, tracer=tracer))

    assert "最大推理步数" in result.content
    assert result.metadata["status"] == "max_iterations_reached"
    assert result.metadata["tool_call_count"] >= 2


def test_context_pressure_trims_long_history():
    plugin = ContextPressurePlugin(max_prompt_tokens=140, pressure_ratio=0.5, min_history_messages=2)
    messages = [{"role": "system", "content": "x" * 20}] + [{"role": "user", "content": "y" * 20}] * 5

    result = plugin.check_pressure(messages)

    assert result["over_threshold"] is True
    assert result["action"] == "trimmed_history"
    assert len(messages) < 6  # trimmed


def test_context_pressure_no_action_when_below_threshold():
    plugin = ContextPressurePlugin(max_prompt_tokens=10000, pressure_ratio=0.8)
    messages = [{"role": "system", "content": "hello"}]

    result = plugin.check_pressure(messages)

    assert result["over_threshold"] is False
    assert result["action"] == "none"
