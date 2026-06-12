from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

    def get(self, schedule_id: str) -> ScheduleItem | None:
        for item in self.list():
            if item.schedule_id == schedule_id:
                return item
        return None

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

    def update(self, schedule_id: str, **changes: Any) -> ScheduleItem | None:
        items = self.list()
        updated: ScheduleItem | None = None
        for item in items:
            if item.schedule_id != schedule_id:
                continue
            for key, value in changes.items():
                if value is not None and hasattr(item, key):
                    setattr(item, key, value)
            updated = item
        if updated:
            self._save(items)
        return updated

    def due(self, now: datetime | None = None) -> list[ScheduleItem]:
        now = now or datetime.now(timezone.utc)
        return [item for item in self.list() if _is_due(item, now)]

    def mark_triggered(self, schedule_id: str, triggered_at: datetime | None = None) -> ScheduleItem | None:
        triggered_at = triggered_at or datetime.now(timezone.utc)
        items = self.list()
        updated: ScheduleItem | None = None
        for item in items:
            if item.schedule_id != schedule_id:
                continue
            item.metadata = {**item.metadata, "last_triggered_at": triggered_at.isoformat()}
            if item.trigger == "once":
                item.enabled = False
            updated = item
        if updated:
            self._save(items)
        return updated

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


def _is_due(item: ScheduleItem, now: datetime) -> bool:
    if not item.enabled:
        return False
    tz = _zoneinfo(item.timezone)
    local_now = now.astimezone(tz)
    last_triggered_at = _parse_dt(item.metadata.get("last_triggered_at"))
    if item.trigger == "once":
        run_at = _parse_dt(item.metadata.get("run_at") or item.cron_expr)
        if run_at is None:
            return last_triggered_at is None
        return last_triggered_at is None and now >= run_at
    if item.trigger == "every":
        interval_seconds = _parse_interval_seconds(item.cron_expr or item.metadata.get("interval") or item.metadata.get("interval_seconds"))
        if interval_seconds <= 0:
            return False
        if last_triggered_at is None:
            return True
        return (now - last_triggered_at).total_seconds() >= interval_seconds
    if item.trigger == "cron":
        return _cron_due(item, local_now, last_triggered_at.astimezone(tz) if last_triggered_at else None)
    return False


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_interval_seconds(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    suffix = text[-1:]
    if suffix in multipliers and text[:-1].isdigit():
        return int(text[:-1]) * multipliers[suffix]
    return 0


def _cron_due(item: ScheduleItem, now: datetime, last_triggered_at: datetime | None) -> bool:
    expr = (item.cron_expr or "").strip()
    if expr == "@daily":
        if last_triggered_at and last_triggered_at.date() == now.date():
            return False
        return True
    if ":" in expr:
        hour_text, minute_text = expr.split(":", 1)
        if not (hour_text.isdigit() and minute_text.isdigit()):
            return False
        due_today = now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
        if now < due_today:
            return False
        return not last_triggered_at or last_triggered_at.date() < now.date()
    return False


def _zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
