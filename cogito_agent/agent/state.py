from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

Role = Literal["system", "user", "assistant", "tool"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass(slots=True)
class InboundMessage:
    message_id: str
    session_id: str
    channel: str
    user_id: str | None
    content: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_cli(cls, content: str, session_id: str = "default") -> "InboundMessage":
        return cls(
            message_id=new_id("msg"),
            session_id=session_id,
            channel="cli",
            user_id=None,
            content=content,
        )


@dataclass(slots=True)
class Message:
    message_id: str
    session_id: str
    trace_id: str | None
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    channel: str = "cli"
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def user(cls, inbound: InboundMessage, trace_id: str) -> "Message":
        return cls(
            message_id=inbound.message_id,
            session_id=inbound.session_id,
            trace_id=trace_id,
            role="user",
            content=inbound.content,
            channel=inbound.channel,
            metadata=inbound.metadata,
        )

    @classmethod
    def assistant(
        cls,
        session_id: str,
        trace_id: str,
        content: str,
        channel: str = "cli",
    ) -> "Message":
        return cls(
            message_id=new_id("msg"),
            session_id=session_id,
            trace_id=trace_id,
            role="assistant",
            content=content,
            channel=channel,
        )

    @classmethod
    def tool(
        cls,
        *,
        session_id: str,
        trace_id: str,
        content: str,
        name: str,
        tool_call_id: str,
        channel: str = "cli",
    ) -> "Message":
        return cls(
            message_id=new_id("msg"),
            session_id=session_id,
            trace_id=trace_id,
            role="tool",
            content=content,
            name=name,
            tool_call_id=tool_call_id,
            channel=channel,
        )


@dataclass(slots=True)
class AgentResponse:
    content: str
    trace_id: str
    session_id: str
    message_id: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    used_memory_ids: list[str] = field(default_factory=list)
    status: str = "ok"
    metadata: dict[str, Any] = field(default_factory=dict)
