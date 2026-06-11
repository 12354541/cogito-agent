from __future__ import annotations

from collections.abc import Callable
from typing import Any


def tool(func: Callable[..., Any]) -> Callable[..., Any]:
    setattr(func, "__cogito_tool__", True)
    return func


def on_tool_pre(func: Callable[..., Any]) -> Callable[..., Any]:
    setattr(func, "__cogito_on_tool_pre__", True)
    return func


def on_tool_result(func: Callable[..., Any]) -> Callable[..., Any]:
    setattr(func, "__cogito_on_tool_result__", True)
    return func
