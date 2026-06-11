from __future__ import annotations

import json
from pathlib import Path

from cogito_agent.agent.state import utc_now_iso


class ProactiveQuota:
    def __init__(self, workspace: Path, daily_limit: int = 5) -> None:
        self.path = workspace / "proactive_quota.json"
        self.daily_limit = daily_limit
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def can_send(self) -> bool:
        state = self._state()
        today = utc_now_iso()[:10]
        return int(state.get(today, 0)) < self.daily_limit

    def mark_sent(self) -> None:
        state = self._state()
        today = utc_now_iso()[:10]
        state[today] = int(state.get(today, 0)) + 1
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def status(self) -> dict[str, int]:
        state = self._state()
        today = utc_now_iso()[:10]
        return {"daily_limit": self.daily_limit, "sent_today": int(state.get(today, 0))}

    def _state(self) -> dict[str, int]:
        return json.loads(self.path.read_text(encoding="utf-8") or "{}")
