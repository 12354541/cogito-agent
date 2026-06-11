from __future__ import annotations

import asyncio

from cogito_agent.tools.calculator import CalculatorTool
from cogito_agent.tools.filesystem import FileReadTool, FileWriteTool
from cogito_agent.tools.registry import ToolRegistry


def test_calculator_tool():
    tool = CalculatorTool()
    result = asyncio.run(tool.execute(expression="128 * 37 + 42"))

    assert result.success is True
    assert result.content == "4778"


def test_filesystem_tool_rejects_outside_workspace(tmp_path):
    registry = ToolRegistry()
    registry.register(FileReadTool(tmp_path))

    result = asyncio.run(registry.execute("read_file", {"path": "..\\secret.txt"}))

    assert result.success is False
    assert "outside workspace" in (result.error or "")


def test_filesystem_tool_reads_workspace_file(tmp_path):
    registry = ToolRegistry()
    registry.register(FileWriteTool(tmp_path))
    registry.register(FileReadTool(tmp_path))

    written = asyncio.run(registry.execute("write_file", {"path": "notes/todo.md", "content": "hello"}))
    read = asyncio.run(registry.execute("read_file", {"path": "notes/todo.md"}))

    assert written.success is True
    assert read.success is True
    assert read.content == "hello"
