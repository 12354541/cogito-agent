from __future__ import annotations

import json
import time
from typing import Any

import httpx

from cogito_agent.agent.state import new_id
from cogito_agent.llm.types import LLMResponse, LLMToolCall
from cogito_agent.llm.provider import LLMProvider
from cogito_agent.tracing.context import TraceContext
from cogito_agent.tracing.redaction import redact_text
from cogito_agent.tracing.tracer import Tracer


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 60.0,
        tracer: Tracer | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.tracer = tracer

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        stream: bool = False,
        trace: TraceContext | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not configured.")
        if stream:
            raise NotImplementedError("Streaming is not implemented yet.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        span = None
        if trace and self.tracer:
            span = self.tracer.start_span(
                trace,
                span_type="llm",
                name="openai_compatible.chat",
                input_preview={
                    "provider": "openai_compatible",
                    "model": self.model,
                    "message_count": len(messages),
                    "visible_tools": [t.get("function", {}).get("name") for t in tools or []],
                },
            )

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            result = LLMResponse(
                content=message.get("content"),
                tool_calls=self._parse_tool_calls(message.get("tool_calls") or []),
                token_usage=data.get("usage") or {},
                metadata={
                    "model": data.get("model", self.model),
                    "finish_reason": data["choices"][0].get("finish_reason"),
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
            )
            if trace and self.tracer and span:
                self.tracer.end_span(
                    trace,
                    span,
                    status="ok",
                    output_preview={
                        "response_preview": (result.content or "")[:200],
                        "tool_calls": [call.name for call in result.tool_calls],
                        "token_usage": result.token_usage,
                    },
                )
            return result
        except Exception as exc:
            if trace and self.tracer and span:
                self.tracer.end_span(trace, span, status="error", error=redact_text(str(exc)))
            raise

    @staticmethod
    def _parse_tool_calls(raw_calls: list[dict[str, Any]]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        for raw in raw_calls:
            function = raw.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    parsed_arguments = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    parsed_arguments = {"__raw_arguments": arguments}
            elif isinstance(arguments, dict):
                parsed_arguments = arguments
            else:
                parsed_arguments = {}
            calls.append(
                LLMToolCall(
                    id=raw.get("id") or new_id("tool_call"),
                    name=function.get("name") or raw.get("name") or "",
                    arguments=parsed_arguments,
                )
            )
        return calls
