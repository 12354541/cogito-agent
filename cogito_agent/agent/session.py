from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from cogito_agent.agent.state import Message
from cogito_agent.tracing.context import TraceContext

if TYPE_CHECKING:
    from cogito_agent.tracing.tracer import Tracer


@dataclass(slots=True)
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)


class SessionManager:
    """In-memory session store for Milestone 1.

    Later milestones can replace this with JSONL or SQLite without changing
    AgentCore's public dependency surface.
    """

    def __init__(self, max_messages: int = 40) -> None:
        self.max_messages = max_messages
        self._sessions: dict[str, Session] = defaultdict(lambda: Session(session_id=""))

    def load(self, session_id: str, trace: TraceContext | None = None, tracer: Tracer | None = None) -> list[Message]:
        session = self._get_or_create(session_id)
        messages = list(session.messages[-self.max_messages :])
        if trace and tracer:
            tracer.record_event(
                trace,
                event="session_loaded",
                metadata={"session_id": session_id, "message_count": len(messages)},
            )
        return messages

    def append(self, message: Message, trace: TraceContext | None = None, tracer: Tracer | None = None) -> None:
        session = self._get_or_create(message.session_id)
        session.messages.append(message)
        if len(session.messages) > self.max_messages:
            session.messages = session.messages[-self.max_messages :]
        if trace and tracer:
            tracer.record_event(
                trace,
                event="session_message_appended",
                metadata={"role": message.role, "message_id": message.message_id},
            )

    def reset(self, session_id: str) -> None:
        self._sessions[session_id] = Session(session_id=session_id)

    def history(self, session_id: str) -> list[Message]:
        return list(self._get_or_create(session_id).messages)

    def extend(self, messages: Iterable[Message]) -> None:
        for message in messages:
            self.append(message)

    def _get_or_create(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None or session.session_id == "":
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
        return session
