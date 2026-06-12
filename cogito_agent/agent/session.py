from __future__ import annotations

from collections import defaultdict
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from cogito_agent.agent.state import Message
from cogito_agent.tracing.context import TraceContext

if TYPE_CHECKING:
    from cogito_agent.tracing.tracer import Tracer


@dataclass(slots=True)
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    state_deltas: list[dict[str, Any]] = field(default_factory=list)


class JSONLSessionStore:
    def __init__(self, workspace: Path) -> None:
        self.session_dir = workspace / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        path = self._path(session_id)
        if not path.exists():
            return session
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("event") == "message_appended":
                session.messages.append(Message(**payload["message"]))
            elif payload.get("event") == "state_delta":
                session.state_deltas.append(payload["delta"])
            elif payload.get("event") == "session_reset":
                session.messages = []
                session.state_deltas.append({"type": "reset", **payload.get("delta", {})})
        return session

    def append_message(self, message: Message) -> None:
        self._append(message.session_id, {"event": "message_appended", "message": asdict(message)})

    def append_state_delta(self, session_id: str, delta: dict[str, Any]) -> None:
        self._append(session_id, {"event": "state_delta", "delta": delta})

    def reset(self, session_id: str) -> None:
        self._append(session_id, {"event": "session_reset", "delta": {}})

    def _append(self, session_id: str, payload: dict[str, Any]) -> None:
        with self._path(session_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in session_id)
        return self.session_dir / f"{safe}.jsonl"


class SessionManager:
    """Session manager with optional JSONL persistence."""

    def __init__(self, max_messages: int = 40, store: JSONLSessionStore | None = None) -> None:
        self.max_messages = max_messages
        self.store = store
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
        if self.store:
            delta = {"type": "message_appended", "role": message.role, "message_id": message.message_id, "trace_id": message.trace_id}
            session.state_deltas.append(delta)
            self.store.append_message(message)
            self.store.append_state_delta(message.session_id, delta)
        if trace and tracer:
            tracer.record_event(
                trace,
                event="session_message_appended",
                metadata={"role": message.role, "message_id": message.message_id, "state_delta": "message_appended"},
            )

    def reset(self, session_id: str) -> None:
        self._sessions[session_id] = Session(session_id=session_id)
        if self.store:
            self.store.reset(session_id)

    def history(self, session_id: str) -> list[Message]:
        return list(self._get_or_create(session_id).messages)

    def state_deltas(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._get_or_create(session_id).state_deltas)

    def extend(self, messages: Iterable[Message]) -> None:
        for message in messages:
            self.append(message)

    def _get_or_create(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None or session.session_id == "":
            session = self.store.load(session_id) if self.store else Session(session_id=session_id)
            if len(session.messages) > self.max_messages:
                session.messages = session.messages[-self.max_messages :]
            self._sessions[session_id] = session
        return session
