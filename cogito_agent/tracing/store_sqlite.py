from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from cogito_agent.agent.state import utc_now_iso


class SQLiteTraceStore:
    """Append-only SQLite trace/event store.

    The schema stays intentionally close to the JSONL event envelope so both
    stores can share Tracer query code.
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.path = workspace / "traces.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def append(self, payload: dict[str, Any]) -> None:
        timestamp = str(payload.get("timestamp") or utc_now_iso())
        event = str(payload.get("event") or "")
        trace_id = str(payload.get("trace_id") or "")
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO trace_events(timestamp, trace_id, event, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (timestamp, trace_id, event, json.dumps(payload, ensure_ascii=False, default=str)),
            )

    def iter_trace(self, trace_id: str) -> Iterable[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT payload_json
                FROM trace_events
                WHERE trace_id = ?
                ORDER BY id ASC
                """,
                (trace_id,),
            ).fetchall()
        for row in rows:
            yield json.loads(row["payload_json"])

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trace_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trace_events_trace_id_id
                ON trace_events(trace_id, id)
                """
            )
