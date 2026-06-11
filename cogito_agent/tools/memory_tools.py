from __future__ import annotations

from typing import Any

from cogito_agent.memory.markdown_store import MarkdownMemoryStore
from cogito_agent.tools.base import Tool, ToolResult


class MemoryWriteTool(Tool):
    name = "memory_write"
    description = "Save a durable user preference or project fact to Markdown memory."
    parameters = {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "Fact or preference to remember."}},
        "required": ["content"],
        "additionalProperties": False,
    }
    risk_level = "write"

    def __init__(self, store: MarkdownMemoryStore) -> None:
        self.store = store

    async def execute(self, **kwargs: Any) -> ToolResult:
        memory_id = self.store.add(str(kwargs["content"]))
        return ToolResult(content=f"Saved memory {memory_id}.", success=True, metadata={"memory_id": memory_id})


class MemoryRecallTool(Tool):
    name = "memory_recall"
    description = "Search long-term Markdown memory."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "top_k": {"type": "integer", "description": "Maximum number of hits."},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    risk_level = "read-only"

    def __init__(self, store: MarkdownMemoryStore) -> None:
        self.store = store

    async def execute(self, **kwargs: Any) -> ToolResult:
        hits = self.store.search(str(kwargs["query"]), top_k=int(kwargs.get("top_k") or 5))
        content = "\n".join(f"{hit.memory_id}: {hit.content_preview}" for hit in hits) or "No memory found."
        return ToolResult(content=content, success=True, metadata={"hit_count": len(hits)})
