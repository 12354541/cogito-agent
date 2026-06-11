from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from cogito_agent.tools.base import Tool, ToolResult


class TimeTool(Tool):
    name = "time_now"
    description = "Return the current time in an IANA timezone."
    parameters = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone, for example Asia/Shanghai or UTC.",
            }
        },
        "required": [],
        "additionalProperties": False,
    }
    risk_level = "read-only"

    async def execute(self, **kwargs: Any) -> ToolResult:
        timezone = str(kwargs.get("timezone") or "Asia/Shanghai")
        try:
            now = datetime.now(ZoneInfo(timezone))
        except Exception as exc:
            return ToolResult(content="", success=False, error=f"Invalid timezone: {exc}")
        return ToolResult(content=now.isoformat(), success=True, metadata={"timezone": timezone})
