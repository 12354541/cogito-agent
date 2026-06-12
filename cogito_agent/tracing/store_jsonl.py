from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from cogito_agent.agent.state import utc_now_iso


class JSONLTraceStore:
    """Append-only JSONL trace/event store."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.trace_dir = workspace / "traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)

    def append(self, payload: dict[str, Any]) -> None:
        today = utc_now_iso()[:10]
        path = self.trace_dir / f"{today}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def iter_trace(self, trace_id: str) -> Iterable[dict[str, Any]]:
        for path in sorted(self.trace_dir.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if payload.get("trace_id") == trace_id:
                        yield payload

    def iter_events(self) -> Iterable[dict[str, Any]]:
        for path in sorted(self.trace_dir.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        yield json.loads(line)
