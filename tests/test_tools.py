from __future__ import annotations

import asyncio

from cogito_agent.tools.calculator import CalculatorTool
from cogito_agent.tools.filesystem import FileReadTool, FileWriteTool
from cogito_agent.tools.registry import ToolRegistry
from cogito_agent.tools.tool_search import ToolSearchTool
from cogito_agent.tools.web import WebFetchTool


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


def test_tool_search_finds_registered_tools():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(ToolSearchTool(registry))

    result = asyncio.run(registry.execute("tool_search", {"query": "calculator"}))

    assert result.success is True
    assert "calculator" in result.content
    assert result.metadata["matches"][0]["name"] == "calculator"


def test_web_fetch_rejects_non_http_url():
    tool = WebFetchTool()

    result = asyncio.run(tool.execute(url="file:///etc/passwd"))

    assert result.success is False
    assert "http" in (result.error or "")
