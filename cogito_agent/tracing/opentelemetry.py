from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OpenTelemetryExporter:
    enabled: bool = False
    service_name: str = "cogito-agent"
    exporter: str = "console"
    endpoint: str = ""
    available: bool = field(default=False, init=False)
    _tracer: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._tracer = None
        self.available = False
        if not self.enabled:
            return
        try:
            from opentelemetry import trace as otel_trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        except Exception:
            return
        provider = TracerProvider(resource=Resource.create({"service.name": self.service_name}))
        span_exporter = ConsoleSpanExporter()
        if self.exporter.lower() == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                span_exporter = OTLPSpanExporter(endpoint=self.endpoint or None)
            except Exception:
                span_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        otel_trace.set_tracer_provider(provider)
        self._tracer = otel_trace.get_tracer(self.service_name)
        self.available = True

    def export_span(self, *, name: str, span_type: str, status: str, attributes: dict[str, Any]) -> None:
        if not self.available or self._tracer is None:
            return
        with self._tracer.start_as_current_span(name) as span:
            span.set_attribute("cogito.span_type", span_type)
            span.set_attribute("cogito.status", status)
            for key, value in attributes.items():
                if isinstance(value, (str, int, float, bool)):
                    span.set_attribute(f"cogito.{key}", value)
