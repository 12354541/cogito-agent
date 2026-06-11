from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
