from __future__ import annotations

from typing import Any

from cogito_agent.tools.base import Tool, ToolResult


class ToolSearchTool(Tool):
    name = "tool_search"
    description = "Search registered tools by name, description, or risk level."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    risk_level = "read-only"

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = str(kwargs["query"]).lower().strip()
        limit = int(kwargs.get("limit") or 5)
        matches: list[dict[str, Any]] = []
        for tool in self.registry.list_tools():
            haystack = f"{tool.name} {tool.description} {tool.risk_level}".lower()
            if query in haystack:
                matches.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "risk_level": tool.risk_level,
                        "enabled": tool.enabled,
                    }
                )
        limited = matches[: max(limit, 1)]
        if not limited:
            return ToolResult(content="No matching tools found.", success=True, metadata={"matches": []})
        content = "\n".join(f"- {item['name']} ({item['risk_level']}): {item['description']}" for item in limited)
        return ToolResult(content=content, success=True, metadata={"matches": limited})
