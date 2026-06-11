"""Tracing package."""

from typing import Any

__all__ = ["TraceContext", "Tracer"]


def __getattr__(name: str) -> Any:
    if name == "TraceContext":
        from cogito_agent.tracing.context import TraceContext

        return TraceContext
    if name == "Tracer":
        from cogito_agent.tracing.tracer import Tracer

        return Tracer
    raise AttributeError(name)
