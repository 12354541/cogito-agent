from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from cogito_agent.agent.state import new_id, utc_now_iso
from cogito_agent.tools.base import Tool, ToolResult


@dataclass(slots=True)
class ScheduleItem:
    schedule_id: str
    name: str
    trigger: Literal["once", "every", "cron"]
    prompt: str
    timezone: str = "Asia/Shanghai"
    cron_expr: str | None = None
    channel: str = "cli"
    enabled: bool = True
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


class ScheduleStore:
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "schedules.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def list(self) -> list[ScheduleItem]:
        data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        return [ScheduleItem(**item) for item in data]

    def add(self, item: ScheduleItem) -> None:
        items = self.list()
        items.append(item)
        self._save(items)

    def cancel(self, schedule_id: str) -> bool:
        items = self.list()
        changed = False
        for item in items:
            if item.schedule_id == schedule_id:
                item.enabled = False
                changed = True
        if changed:
            self._save(items)
        return changed

    def _save(self, items: list[ScheduleItem]) -> None:
        self.path.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")


class ScheduleCreateTool(Tool):
    name = "schedule_create"
    description = "Create a local reminder or scheduled task."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "prompt": {"type": "string"},
            "trigger": {"type": "string", "enum": ["once", "every", "cron"]},
            "cron_expr": {"type": "string"},
            "timezone": {"type": "string"},
        },
        "required": ["name", "prompt", "trigger"],
        "additionalProperties": False,
    }
    risk_level = "write"

    def __init__(self, store: ScheduleStore) -> None:
        self.store = store

    async def execute(self, **kwargs: Any) -> ToolResult:
        item = ScheduleItem(
            schedule_id=new_id("schedule"),
            name=str(kwargs["name"]),
            prompt=str(kwargs["prompt"]),
            trigger=kwargs["trigger"],
            cron_expr=kwargs.get("cron_expr"),
            timezone=str(kwargs.get("timezone") or "Asia/Shanghai"),
        )
        self.store.add(item)
        return ToolResult(content=f"Created schedule {item.schedule_id}.", success=True, metadata={"schedule_id": item.schedule_id})
