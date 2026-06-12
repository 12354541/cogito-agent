from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cogito_agent.agent.state import utc_now_iso


class ProactiveQuota:
    def __init__(self, workspace: Path, daily_limit: int = 5, cooldown_seconds: int = 3600, quiet_hours: str = "") -> None:
        self.path = workspace / "proactive_quota.json"
        self.daily_limit = daily_limit
        self.cooldown_seconds = cooldown_seconds
        self.quiet_hours = quiet_hours
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def can_send(self) -> bool:
        return self.block_reason() is None

    def block_reason(self) -> str | None:
        if self._in_quiet_hours():
            return "quiet_hours"
        state = self._state()
        today = utc_now_iso()[:10]
        if int(state.get(today, 0)) >= self.daily_limit:
            return "quota_exceeded"
        last_sent_at = _parse_dt(state.get("last_sent_at"))
        if last_sent_at and (datetime.now(timezone.utc) - last_sent_at).total_seconds() < self.cooldown_seconds:
            return "cooldown"
        return None

    def mark_sent(self) -> None:
        state = self._state()
        today = utc_now_iso()[:10]
        state[today] = int(state.get(today, 0)) + 1
        state["last_sent_at"] = utc_now_iso()
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def status(self) -> dict[str, object]:
        state = self._state()
        today = utc_now_iso()[:10]
        return {
            "daily_limit": self.daily_limit,
            "sent_today": int(state.get(today, 0)),
            "cooldown_seconds": self.cooldown_seconds,
            "quiet_hours": self.quiet_hours,
            "last_sent_at": state.get("last_sent_at"),
            "block_reason": self.block_reason(),
        }

    def _state(self) -> dict[str, object]:
        return json.loads(self.path.read_text(encoding="utf-8") or "{}")

    def _in_quiet_hours(self) -> bool:
        if not self.quiet_hours or "-" not in self.quiet_hours:
            return False
        start_text, end_text = self.quiet_hours.split("-", 1)
        start = _parse_clock(start_text)
        end = _parse_clock(end_text)
        if start is None or end is None:
            return False
        now = datetime.now().time()
        if start <= end:
            return start <= now < end
        return now >= start or now < end


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_clock(value: str):
    import datetime as dt

    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return dt.time(hour=int(parts[0]), minute=int(parts[1]))
