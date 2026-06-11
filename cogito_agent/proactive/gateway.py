from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(slots=True)
class ProactiveItem:
    item_id: str
    channel: Literal["alert", "content", "context"]
    title: str
    body: str
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class DataGateway:
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "proactive_sources.json"
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def fetch(self) -> list[ProactiveItem]:
        data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        return [ProactiveItem(**item) for item in data]
