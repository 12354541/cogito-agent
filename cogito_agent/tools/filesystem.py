from __future__ import annotations

from pathlib import Path
from typing import Any

from cogito_agent.tools.base import Tool, ToolResult


class WorkspaceFileToolMixin:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _resolve_workspace_path(self, path: str) -> Path:
        candidate = (self.workspace / path).resolve()
        if self.workspace != candidate and self.workspace not in candidate.parents:
            raise PermissionError("Path is outside workspace.")
        return candidate


class FileReadTool(WorkspaceFileToolMixin, Tool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to workspace."},
            "max_chars": {"type": "integer", "description": "Maximum characters to return."},
        },
        "required": ["path"],
        "additionalProperties": False,
    }
    risk_level = "read-only"

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = self._resolve_workspace_path(str(kwargs["path"]))
            max_chars = int(kwargs.get("max_chars") or 8000)
            content = path.read_text(encoding="utf-8")[:max_chars]
            return ToolResult(content=content, success=True, metadata={"path": str(path), "chars": len(content)})
        except Exception as exc:
            return ToolResult(content="", success=False, error=str(exc))


class FileWriteTool(WorkspaceFileToolMixin, Tool):
    name = "write_file"
    description = "Write a UTF-8 text file inside the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to workspace."},
            "content": {"type": "string", "description": "Text content to write."},
            "overwrite": {"type": "boolean", "description": "Set true to overwrite an existing file."},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }
    risk_level = "write"

    def __init__(self, workspace: Path, require_approval_for_write: bool = False) -> None:
        super().__init__(workspace)
        self.require_approval_for_write = require_approval_for_write

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = self._resolve_workspace_path(str(kwargs["path"]))
            path.parent.mkdir(parents=True, exist_ok=True)
            content = str(kwargs["content"])
            overwrite = bool(kwargs.get("overwrite", False))
            if self.require_approval_for_write and not overwrite:
                return ToolResult(content="", success=False, error="Write approval is required; pass overwrite=true after approval.")
            if path.exists() and not overwrite:
                return ToolResult(content="", success=False, error="File already exists; pass overwrite=true to replace it.")
            path.write_text(content, encoding="utf-8")
            return ToolResult(content=f"Wrote {len(content)} characters to {path.name}.", success=True, metadata={"path": str(path), "overwrite": overwrite})
        except Exception as exc:
            return ToolResult(content="", success=False, error=str(exc))
