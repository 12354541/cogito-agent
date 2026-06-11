from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from cogito_agent.agent.state import utc_now_iso


@dataclass(slots=True)
class TraceRecord:
    trace_id: str
    session_id: str
    user_message_preview: str
    final_response_preview: str | None = None
    status: str = "running"
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: str | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TraceSpan:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    span_type: str
    name: str
    input_preview: dict[str, Any] = field(default_factory=dict)
    output_preview: dict[str, Any] = field(default_factory=dict)
    status: str = "running"
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
