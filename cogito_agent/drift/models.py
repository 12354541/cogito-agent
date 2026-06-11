from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DriftSkill:
    name: str
    description: str
    path: Path
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DriftRunResult:
    skill_name: str | None
    status: str
    message_result: str = "silent"
    details: dict[str, Any] = field(default_factory=dict)
