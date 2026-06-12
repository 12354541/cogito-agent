from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from cogito_agent.tools.base import Tool, ToolResult


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a public HTTP/HTTPS URL and return a bounded text preview."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer"},
        },
        "required": ["url"],
        "additionalProperties": False,
    }
    risk_level = "network"

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = str(kwargs["url"]).strip()
        max_chars = int(kwargs.get("max_chars") or 4000)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ToolResult(content="", success=False, error="Only http and https URLs are allowed.")
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        text = response.text[: max(max_chars, 1)]
        return ToolResult(
            content=text,
            success=True,
            metadata={
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "truncated": len(response.text) > len(text),
            },
        )
