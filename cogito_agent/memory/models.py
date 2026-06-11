from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryHit:
    memory_id: str
    source: str
    content_preview: str
    score: float
    injected: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RagHit:
    doc_id: str
    source: str
    content_preview: str
    score: float
    injected: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
