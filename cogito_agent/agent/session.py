from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
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


class SessionStore(ABC):
    @abstractmethod
    def load(self, session_id: str) -> Session: ...

    @abstractmethod
    def append_message(self, message: Message) -> None: ...

    @abstractmethod
    def append_state_delta(self, session_id: str, delta: dict[str, Any]) -> None: ...

    @abstractmethod
    def reset(self, session_id: str) -> None: ...


class JSONLSessionStore(SessionStore):
    def __init__(self, workspace: Path) -> None:
        self.session_dir = workspace / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}

    def _lock_for(self, session_id: str) -> threading.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = threading.Lock()
        return self._locks[session_id]

    def load(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        path = self._path(session_id)
        if not path.exists():
            return session
        with self._lock_for(session_id):
            raw = path.read_text(encoding="utf-8")
        for line in raw.splitlines():
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
        with self._lock_for(session_id):
            with self._path(session_id).open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in session_id)
        return self.session_dir / f"{safe}.jsonl"


class SQLiteSessionStore(SessionStore):
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "sessions.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    trace_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    name TEXT,
                    tool_call_id TEXT,
                    channel TEXT DEFAULT 'cli',
                    created_at TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, id);

                CREATE TABLE IF NOT EXISTS state_deltas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    delta_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_deltas_session
                    ON state_deltas(session_id, id);
            """)

    def load(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            for row in rows:
                session.messages.append(Message(
                    message_id=row["message_id"],
                    session_id=row["session_id"],
                    trace_id=row["trace_id"],
                    role=row["role"],
                    content=row["content"],
                    name=row["name"],
                    tool_call_id=row["tool_call_id"],
                    channel=row["channel"],
                    created_at=row["created_at"],
                    metadata=json.loads(row["metadata_json"]),
                ))
            delta_rows = conn.execute(
                "SELECT delta_json FROM state_deltas WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            for row in delta_rows:
                session.state_deltas.append(json.loads(row["delta_json"]))
        return session

    def append_message(self, message: Message) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """INSERT INTO messages
                   (session_id, message_id, trace_id, role, content,
                    name, tool_call_id, channel, created_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message.session_id,
                    message.message_id,
                    message.trace_id,
                    message.role,
                    message.content,
                    message.name,
                    message.tool_call_id,
                    message.channel,
                    message.created_at,
                    json.dumps(message.metadata, ensure_ascii=False, default=str),
                ),
            )

    def append_state_delta(self, session_id: str, delta: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO state_deltas (session_id, delta_json) VALUES (?, ?)",
                (session_id, json.dumps(delta, ensure_ascii=False, default=str)),
            )

    def reset(self, session_id: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute(
                "INSERT INTO state_deltas (session_id, delta_json) VALUES (?, ?)",
                (session_id, json.dumps({"type": "reset"})),
            )


class MemorySessionStore(SessionStore):
    """In-memory store for tests. Does not persist across restarts."""

    def __init__(self) -> None:
        self._messages: dict[str, list[Message]] = {}
        self._deltas: dict[str, list[dict[str, Any]]] = {}

    def load(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        session.messages = list(self._messages.get(session_id, []))
        session.state_deltas = list(self._deltas.get(session_id, []))
        return session

    def append_message(self, message: Message) -> None:
        self._messages.setdefault(message.session_id, []).append(message)

    def append_state_delta(self, session_id: str, delta: dict[str, Any]) -> None:
        self._deltas.setdefault(session_id, []).append(delta)

    def reset(self, session_id: str) -> None:
        self._messages[session_id] = []
        self._deltas[session_id] = [{"type": "reset"}]


class SessionManager:
    """Session manager backed by a SessionStore (JSONL, SQLite, or Memory)."""

    def __init__(self, store: SessionStore, max_messages: int = 40) -> None:
        self.store = store
        self.max_messages = max_messages
        self._cache: dict[str, Session] = {}

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

        delta: dict[str, Any] = {
            "type": "message_appended",
            "role": message.role,
            "message_id": message.message_id,
            "trace_id": message.trace_id,
        }
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
        self.store.reset(session_id)
        self._cache[session_id] = Session(session_id=session_id)

    def history(self, session_id: str) -> list[Message]:
        return list(self._get_or_create(session_id).messages)

    def state_deltas(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._get_or_create(session_id).state_deltas)

    def extend(self, messages: Iterable[Message]) -> None:
        for message in messages:
            self.append(message)

    def _get_or_create(self, session_id: str) -> Session:
        if session_id not in self._cache:
            session = self.store.load(session_id)
            if len(session.messages) > self.max_messages:
                session.messages = session.messages[-self.max_messages :]
            self._cache[session_id] = session
        return self._cache[session_id]
