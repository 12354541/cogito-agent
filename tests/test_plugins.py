from __future__ import annotations

import asyncio

from cogito_agent.plugins.builtin.tool_loop_guard import ToolLoopGuardPlugin
from cogito_agent.plugins.manager import PluginManager
from cogito_agent.tools.calculator import CalculatorTool
from cogito_agent.tools.registry import ToolRegistry


def test_tool_loop_guard_blocks_repeated_call():
    plugin_manager = PluginManager([ToolLoopGuardPlugin(max_same_call=1)])
    registry = ToolRegistry(plugin_manager=plugin_manager)
    registry.register(CalculatorTool())

    first = asyncio.run(registry.execute("calculator", {"expression": "2+2"}))
    second = asyncio.run(registry.execute("calculator", {"expression": "2+2"}))

    assert first.success is True
    assert second.success is False
    assert "repeated" in (second.error or "")
