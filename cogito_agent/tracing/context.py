from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TraceContext:
    trace_id: str
    session_id: str
    root_span_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
