from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cogito_agent.agent.core import AgentCore
from cogito_agent.agent.state import AgentResponse, InboundMessage, new_id


@dataclass(slots=True)
class SubAgentTask:
    name: str
    content: str
    parent_trace_id: str
    parent_session_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


class SubAgentRunner:
    """Runs a scoped child task while preserving parent/child trace linkage."""

    def __init__(self, agent: AgentCore) -> None:
        self.agent = agent

    async def run(self, task: SubAgentTask) -> AgentResponse:
        child_session_id = f"{task.parent_session_id}:sub:{task.name}"
        inbound = InboundMessage(
            message_id=new_id("submsg"),
            session_id=child_session_id,
            channel="subagent",
            user_id=None,
            content=task.content,
            metadata={
                "parent_trace_id": task.parent_trace_id,
                "subagent_name": task.name,
                **task.metadata,
            },
        )
        response = await self.agent.process(inbound)
        self.agent.tracer.record_trace_link(
            parent_trace_id=task.parent_trace_id,
            child_trace_id=response.trace_id,
            relation="subagent",
            metadata={"subagent_name": task.name, "child_session_id": child_session_id},
        )
        return response
