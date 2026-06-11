from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

RiskLevel = Literal["read-only", "write", "network", "shell", "external-send"]


@dataclass(slots=True)
class ToolResult:
    content: str
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    risk_level: RiskLevel = "read-only"
    enabled: bool = True

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError
