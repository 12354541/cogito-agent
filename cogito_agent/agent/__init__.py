"""Agent runtime package."""

from typing import Any

__all__ = [
    "AgentCore",
    "AgentResponse",
    "InboundMessage",
    "Message",
    "RuleBasedReasoner",
    "LLMReasoner",
    "SessionManager",
    "SubAgentRunner",
    "SubAgentTask",
]


def __getattr__(name: str) -> Any:
    if name == "AgentCore":
        from cogito_agent.agent.core import AgentCore

        return AgentCore
    if name in {"RuleBasedReasoner", "LLMReasoner"}:
        from cogito_agent.agent.reasoner import LLMReasoner, RuleBasedReasoner

        return {"RuleBasedReasoner": RuleBasedReasoner, "LLMReasoner": LLMReasoner}[name]
    if name == "SessionManager":
        from cogito_agent.agent.session import SessionManager

        return SessionManager
    if name in {"SubAgentRunner", "SubAgentTask"}:
        from cogito_agent.agent.subagent import SubAgentRunner, SubAgentTask

        return {"SubAgentRunner": SubAgentRunner, "SubAgentTask": SubAgentTask}[name]
    if name in {"AgentResponse", "InboundMessage", "Message"}:
        from cogito_agent.agent.state import AgentResponse, InboundMessage, Message

        return {"AgentResponse": AgentResponse, "InboundMessage": InboundMessage, "Message": Message}[name]
    raise AttributeError(name)
