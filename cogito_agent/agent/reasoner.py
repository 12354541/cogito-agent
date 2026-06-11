from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cogito_agent.agent.state import Message
from cogito_agent.llm.provider import LLMProvider
from cogito_agent.llm.types import LLMToolCall
from cogito_agent.memory.retriever import MemoryRetriever, RetrievalResult
from cogito_agent.prompting.manager import PromptManager
from cogito_agent.tools.registry import ToolRegistry
from cogito_agent.tracing.context import TraceContext

if TYPE_CHECKING:
    from cogito_agent.tracing.tracer import Tracer


@dataclass(slots=True)
class ReasonerResult:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    used_memory_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class RuleBasedReasoner:
    """Fallback reasoner used when no real LLM key is configured."""

    async def run(
        self,
        *,
        history: list[Message],
        user_content: str,
        trace: TraceContext,
        tracer: "Tracer",
    ) -> ReasonerResult:
        span = tracer.start_span(
            trace,
            span_type="reasoner",
            name="rule_based_reasoner.run",
            input_preview={"user_content": user_content[:200], "history_count": len(history)},
        )
        answer = f"我收到了你的消息：{user_content}"
        tracer.end_span(trace, span, status="ok", output_preview={"content": answer[:200]})
        return ReasonerResult(content=answer, metadata={"steps": 1, "mode": "rule_based"})


class LLMReasoner:
    """LLM + tool-calling loop."""

    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        prompt_manager: PromptManager,
        tool_registry: ToolRegistry,
        memory_retriever: MemoryRetriever | None = None,
        max_iterations: int = 8,
    ) -> None:
        self.llm_provider = llm_provider
        self.prompt_manager = prompt_manager
        self.tool_registry = tool_registry
        self.memory_retriever = memory_retriever
        self.max_iterations = max_iterations

    async def run(
        self,
        *,
        history: list[Message],
        user_content: str,
        trace: TraceContext,
        tracer: "Tracer",
    ) -> ReasonerResult:
        retrieval = self.memory_retriever.search(user_content, trace=trace, tracer=tracer) if self.memory_retriever else RetrievalResult()
        prompt = self.prompt_manager.render(history=history, user_message=user_content, memory_hits=retrieval.all_prompt_hits())
        tracer.record_event(trace, event="prompt_rendered", metadata=prompt.metadata)

        messages: list[dict[str, Any]] = list(prompt.messages)
        visible_tools = self.tool_registry.openai_tools()
        tool_calls_summary: list[dict[str, Any]] = []

        for step in range(1, self.max_iterations + 1):
            tracer.record_event(trace, event="reasoner_step_started", metadata={"step": step})
            llm_response = await self.llm_provider.chat(messages, tools=visible_tools, trace=trace)

            if llm_response.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": llm_response.content,
                        "tool_calls": [_tool_call_to_openai(call) for call in llm_response.tool_calls],
                    }
                )
                for call in llm_response.tool_calls:
                    result = await self.tool_registry.execute(call.name, call.arguments, trace=trace, tracer=tracer)
                    result_content = result.content if result.success else f"Tool error: {result.error}"
                    tool_calls_summary.append(
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                            "success": result.success,
                            "error": result.error,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": result_content,
                        }
                    )
                continue

            content = llm_response.content or ""
            tracer.record_event(trace, event="final_answer", metadata={"step": step, "preview": content[:200]})
            return ReasonerResult(
                content=content,
                tool_calls=tool_calls_summary,
                used_memory_ids=[hit.memory_id for hit in retrieval.memory_hits],
                metadata={
                    "steps": step,
                    "model": llm_response.metadata.get("model"),
                    "prompt_hash": prompt.prompt_hash,
                    "token_usage": llm_response.token_usage,
                    "used_doc_ids": [hit.doc_id for hit in retrieval.doc_hits],
                },
            )

        return ReasonerResult(
            content="已达到最大推理步数，任务未能完成。",
            tool_calls=tool_calls_summary,
            used_memory_ids=[hit.memory_id for hit in retrieval.memory_hits],
            metadata={
                "steps": self.max_iterations,
                "status": "max_iterations_reached",
                "used_doc_ids": [hit.doc_id for hit in retrieval.doc_hits],
            },
        )


def _tool_call_to_openai(call: LLMToolCall) -> dict[str, Any]:
    import json

    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
    }
