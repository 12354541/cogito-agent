from __future__ import annotations

import asyncio

from cogito_agent.tools.base import Tool, ToolResult
from cogito_agent.tools.calculator import CalculatorTool
from cogito_agent.tools.filesystem import FileReadTool, FileWriteTool
from cogito_agent.tools.memory_tools import MemoryWriteTool
from cogito_agent.tools.registry import ToolRegistry
from cogito_agent.tools.tool_search import ToolSearchTool
from cogito_agent.tools.web import WebFetchTool
from cogito_agent.tracing.redaction import sanitize_tool_arguments, sanitize_tool_result


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


def test_filesystem_tool_requires_overwrite_for_existing_file(tmp_path):
    registry = ToolRegistry()
    registry.register(FileWriteTool(tmp_path))

    first = asyncio.run(registry.execute("write_file", {"path": "notes/todo.md", "content": "hello"}))
    second = asyncio.run(registry.execute("write_file", {"path": "notes/todo.md", "content": "replace"}))
    third = asyncio.run(registry.execute("write_file", {"path": "notes/todo.md", "content": "replace", "overwrite": True}))

    assert first.success is True
    assert second.success is False
    assert "overwrite=true" in (second.error or "")
    assert third.success is True


class SlowTool(Tool):
    name = "slow"
    description = "Slow test tool"
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    timeout_seconds = 0.01

    async def execute(self, **kwargs):
        await asyncio.sleep(0.1)
        return ToolResult(content="done", success=True)


def test_tool_registry_times_out_tools():
    registry = ToolRegistry()
    registry.register(SlowTool())

    result = asyncio.run(registry.execute("slow", {}))

    assert result.success is False
    assert "timed out" in (result.error or "")


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


# --- Trace sanitization security tests (P0) ---

def test_sanitize_hides_file_write_content(tmp_path):
    tool = FileWriteTool(tmp_path)
    args = {"path": "secret.txt", "content": "my-api-key-is-sk-abc123def456"}
    sanitized = sanitize_tool_arguments(tool, args)
    assert sanitized["path"] == "secret.txt"
    assert "sk-abc123def456" not in sanitized["content"]
    assert "[REDACTED]" in sanitized["content"] or "sha256=" in sanitized["content"]


def test_sanitize_hides_memory_write_content(tmp_path):
    from cogito_agent.memory.markdown_store import MarkdownMemoryStore
    store = MarkdownMemoryStore(tmp_path)
    tool = MemoryWriteTool(store)
    sanitized = sanitize_tool_arguments(tool, {"content": "My password is hunter2"})
    assert "sha256=" in sanitized["content"]
    assert "len=" in sanitized["content"]
    assert sanitized["content"] != "My password is hunter2"  # not stored verbatim


def test_trace_span_does_not_contain_raw_secret(tmp_path):
    from cogito_agent.tracing.tracer import Tracer
    tracer = Tracer(workspace=tmp_path)
    registry = ToolRegistry()
    registry.register(FileWriteTool(tmp_path))
    trace = tracer.start_trace(session_id="test", user_message_preview="write secret")
    result = asyncio.run(registry.execute(
        "write_file",
        {"path": "secret.txt", "content": "sk-my-real-secret-key", "overwrite": True},
        trace=trace,
        tracer=tracer,
    ))
    assert result.success is True
    steps = tracer.get_trace_steps(trace.trace_id)
    tool_spans = [s for s in steps if s.get("span_type") == "tool"]
    assert len(tool_spans) >= 1
    arg_text = str(tool_spans[0].get("input_preview", {}))
    assert "sk-my-real-secret-key" not in arg_text
    assert "sha256=" in arg_text or "[REDACTED]" in arg_text


def test_trace_tool_result_truncates_large_content(tmp_path):
    from cogito_agent.tracing.tracer import Tracer
    tracer = Tracer(workspace=tmp_path)
    registry = ToolRegistry()
    registry.register(FileWriteTool(tmp_path))
    trace = tracer.start_trace(session_id="test", user_message_preview="large write")
    long_content = "A" * 10000
    result = asyncio.run(registry.execute(
        "write_file",
        {"path": "large.txt", "content": long_content, "overwrite": True},
        trace=trace,
        tracer=tracer,
    ))
    assert result.success is True
    steps = tracer.get_trace_steps(trace.trace_id)
    tool_spans = [s for s in steps if s.get("span_type") == "tool"]
    assert len(tool_spans) >= 1
    inp = tool_spans[0].get("input_preview", {})
    content_preview = str(inp.get("arguments", {}))
    assert "10000" in content_preview
    assert "A" * 10000 not in content_preview  # full content not in trace
    assert "sha256=" in content_preview or "len=" in content_preview


def test_sanitize_redacts_sk_key_from_any_arg():
    class GenericTool(Tool):
        name = "generic"
        description = "test"
        parameters = {"type": "object", "properties": {}, "additionalProperties": False}
        async def execute(self, **kwargs):
            return ToolResult(content="ok", success=True)
    tool = GenericTool()
    sanitized = sanitize_tool_arguments(tool, {"api_key": "sk-12345678", "safe_arg": "hello"})
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["safe_arg"] == "hello"


def test_sanitize_url_is_previewed_not_full():
    tool = WebFetchTool()
    sanitized = sanitize_tool_arguments(tool, {"url": "https://example.com/very/long/path?q=1234567890"})
    assert "example.com" in sanitized["url"]
    assert len(sanitized["url"]) <= 250  # max_preview_chars=200 + annotation
