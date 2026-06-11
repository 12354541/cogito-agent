from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cogito_agent.agent.state import utc_now_iso
from cogito_agent.tracing.context import TraceContext
from cogito_agent.tracing.models import TraceRecord, TraceSpan
from cogito_agent.tracing.redaction import redact_mapping, redact_text
from cogito_agent.tracing.store_jsonl import JSONLTraceStore


def _new_trace_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"trace_{stamp}_{uuid4().hex[:8]}"


def _new_span_id() -> str:
    return f"span_{uuid4().hex[:12]}"


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _duration_ms(started_at: str, ended_at: str) -> int:
    return int((_parse_iso(ended_at) - _parse_iso(started_at)).total_seconds() * 1000)


class Tracer:
    """Creates TraceContext and writes trace/span events to JSONL."""

    def __init__(self, workspace: Path) -> None:
        self.store = JSONLTraceStore(workspace=workspace)
        self.last_trace_id: str | None = None
        self._records: dict[str, TraceRecord] = {}
        self._spans: dict[str, list[TraceSpan]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}

    def start_trace(
        self,
        *,
        session_id: str,
        user_message_preview: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext:
        trace_id = _new_trace_id()
        root_span_id = _new_span_id()
        record = TraceRecord(
            trace_id=trace_id,
            session_id=session_id,
            user_message_preview=user_message_preview,
            metadata=redact_mapping(metadata or {}),
        )
        context = TraceContext(trace_id=trace_id, session_id=session_id, root_span_id=root_span_id)
        self.last_trace_id = trace_id
        self._records[trace_id] = record
        self._spans[trace_id] = []
        self._events[trace_id] = []
        self._write("trace_started", trace_id, record.to_dict())
        return context

    def finish_trace(
        self,
        trace: TraceContext,
        *,
        status: str,
        final_response_preview: str | None = None,
    ) -> None:
        record = self._records[trace.trace_id]
        record.status = status
        record.final_response_preview = final_response_preview
        record.ended_at = utc_now_iso()
        record.duration_ms = _duration_ms(record.started_at, record.ended_at)
        self._write("trace_finished", trace.trace_id, record.to_dict())

    def start_span(
        self,
        trace: TraceContext,
        *,
        span_type: str,
        name: str,
        input_preview: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        span = TraceSpan(
            span_id=_new_span_id(),
            trace_id=trace.trace_id,
            parent_span_id=trace.root_span_id,
            span_type=span_type,
            name=name,
            input_preview=redact_mapping(input_preview or {}),
            metadata=redact_mapping(metadata or {}),
        )
        self._spans[trace.trace_id].append(span)
        self._write("span_started", trace.trace_id, span.to_dict())
        return span

    def end_span(
        self,
        trace: TraceContext,
        span: TraceSpan,
        *,
        status: str,
        output_preview: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        span.status = status
        span.output_preview = redact_mapping(output_preview or {})
        span.error = redact_text(error) if error else None
        span.ended_at = utc_now_iso()
        span.duration_ms = _duration_ms(span.started_at, span.ended_at)
        self._write("span_finished", trace.trace_id, span.to_dict())

    def record_event(
        self,
        trace: TraceContext,
        *,
        event: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "trace_id": trace.trace_id,
            "session_id": trace.session_id,
            "event": event,
            "timestamp": utc_now_iso(),
            "metadata": redact_mapping(metadata or {}),
        }
        self._events.setdefault(trace.trace_id, []).append(payload)
        self._write(event, trace.trace_id, payload)

    def get_last_trace_summary(self) -> str:
        if self.last_trace_id is None:
            return "暂无 trace。"
        return self.get_trace_summary(self.last_trace_id)

    def get_trace_summary(self, trace_id: str) -> str:
        record = self._records.get(trace_id)
        if record is None:
            return f"未找到 trace：{trace_id}"

        lines = [
            f"trace_id: {record.trace_id}",
            f"session_id: {record.session_id}",
            f"status: {record.status}",
            f"duration_ms: {record.duration_ms}",
            f"user_input: {record.user_message_preview}",
            f"final_response: {record.final_response_preview}",
            "events:",
        ]
        for event in self._events.get(trace_id, []):
            lines.append(f"  - {event['event']}: {event.get('metadata', {})}")
        lines.append("spans:")
        for span in self._spans.get(trace_id, []):
            lines.append(
                f"  - {span.span_type}/{span.name}: {span.status}, "
                f"duration_ms={span.duration_ms}, error={span.error}"
            )
        return "\n".join(lines)

    def _write(self, event: str, trace_id: str, payload: dict[str, Any]) -> None:
        self.store.append(
            {
                "timestamp": utc_now_iso(),
                "event": event,
                "trace_id": trace_id,
                "payload": redact_mapping(payload),
            }
        )
