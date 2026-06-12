from __future__ import annotations

from typing import Any

from cogito_agent.agent.reasoner import ReasonerResult, RuleBasedReasoner
from cogito_agent.agent.session import SessionManager
from cogito_agent.agent.state import AgentResponse, InboundMessage, Message
from cogito_agent.memory.consolidation import MemoryConsolidator
from cogito_agent.plugins.manager import PluginManager
from cogito_agent.tracing.redaction import redact_text
from cogito_agent.tracing.tracer import Tracer


class AgentCore:
    """Unified entrypoint for inbound messages."""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        tracer: Tracer,
        reasoner: Any | None = None,
        plugin_manager: PluginManager | None = None,
        memory_consolidator: MemoryConsolidator | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.reasoner = reasoner or RuleBasedReasoner()
        self.tracer = tracer
        self.plugin_manager = plugin_manager or PluginManager()
        self.memory_consolidator = memory_consolidator

    async def process(self, inbound: InboundMessage) -> AgentResponse:
        trace = self.tracer.start_trace(
            session_id=inbound.session_id,
            user_message_preview=inbound.content[:200],
            metadata={"channel": inbound.channel, "message_id": inbound.message_id, **inbound.metadata},
        )

        try:
            self.tracer.record_event(
                trace,
                event="user_input",
                metadata={"message_id": inbound.message_id, "preview": inbound.content[:200]},
            )

            history = self.session_manager.load(inbound.session_id, trace=trace, tracer=self.tracer)
            user_message = Message.user(inbound, trace_id=trace.trace_id)
            self.session_manager.append(user_message, trace=trace, tracer=self.tracer)
            if self.memory_consolidator and self.memory_consolidator.maybe_enqueue_user_message(inbound.content, trace_id=trace.trace_id):
                self.tracer.record_event(trace, event="memory_pending_enqueued", metadata={"preview": inbound.content[:120]})

            await self.plugin_manager.run_phase(
                "before_turn",
                inbound=inbound,
                history=history,
                trace=trace,
                tracer=self.tracer,
            )

            result = await self.reasoner.run(
                history=history,
                user_content=inbound.content,
                trace=trace,
                tracer=self.tracer,
            )
            if isinstance(result, str):
                result = ReasonerResult(content=result, metadata={"steps": 1})

            await self.plugin_manager.run_phase(
                "after_reasoning",
                inbound=inbound,
                result=result,
                trace=trace,
                tracer=self.tracer,
            )

            assistant_message = Message.assistant(
                session_id=inbound.session_id,
                trace_id=trace.trace_id,
                content=result.content,
                channel=inbound.channel,
            )
            self.session_manager.append(assistant_message, trace=trace, tracer=self.tracer)

            await self.plugin_manager.run_phase(
                "after_turn",
                inbound=inbound,
                response=result,
                trace=trace,
                tracer=self.tracer,
            )

            self.tracer.record_event(
                trace,
                event="final_response_created",
                metadata={"preview": result.content[:200]},
            )
            self.tracer.finish_trace(trace, status="ok", final_response_preview=result.content[:200])

            return AgentResponse(
                content=result.content,
                trace_id=trace.trace_id,
                session_id=inbound.session_id,
                message_id=assistant_message.message_id,
                tool_calls=result.tool_calls,
                used_memory_ids=result.used_memory_ids,
                metadata=result.metadata,
            )
        except Exception as exc:
            sanitized_error = redact_text(str(exc))
            error_message = f"执行失败：{sanitized_error}"
            self.tracer.record_event(trace, event="error_occurred", metadata={"error": sanitized_error})
            self.tracer.finish_trace(trace, status="error", final_response_preview=error_message[:200])
            return AgentResponse(
                content=error_message,
                trace_id=trace.trace_id,
                session_id=inbound.session_id,
                message_id=inbound.message_id,
                status="error",
                metadata={"error": sanitized_error},
            )
