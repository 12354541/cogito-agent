from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cogito_agent.agent.state import utc_now_iso
from cogito_agent.tracing.context import TraceContext
from cogito_agent.tracing.models import TraceRecord, TraceSpan
from cogito_agent.tracing.opentelemetry import OpenTelemetryExporter
from cogito_agent.tracing.redaction import redact_mapping, redact_text
from cogito_agent.tracing.store_jsonl import JSONLTraceStore
from cogito_agent.tracing.store_sqlite import SQLiteTraceStore


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

    def __init__(
        self,
        workspace: Path,
        store: str = "jsonl",
        *,
        otel_enabled: bool = False,
        otel_service_name: str = "cogito-agent",
    ) -> None:
        self.store = _build_store(workspace=workspace, store=store)
        self.otel = OpenTelemetryExporter(enabled=otel_enabled, service_name=otel_service_name)
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
        self.otel.export_span(
            name=span.name,
            span_type=span.span_type,
            status=span.status,
            attributes={
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "duration_ms": span.duration_ms or 0,
                "error": span.error or "",
            },
        )

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

    def record_trace_link(
        self,
        *,
        parent_trace_id: str,
        child_trace_id: str,
        relation: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "trace_id": parent_trace_id,
            "event": "trace_link_created",
            "timestamp": utc_now_iso(),
            "metadata": redact_mapping(
                {
                    "parent_trace_id": parent_trace_id,
                    "child_trace_id": child_trace_id,
                    "relation": relation,
                    **(metadata or {}),
                }
            ),
        }
        self._events.setdefault(parent_trace_id, []).append(payload)
        self._write("trace_link_created", parent_trace_id, payload)

    def get_last_trace_summary(self) -> str:
        if self.last_trace_id is None:
            return "暂无 trace。"
        return self.get_trace_summary(self.last_trace_id)

    def get_trace_summary(self, trace_id: str) -> str:
        record = self._records.get(trace_id) or self._load_record_from_store(trace_id)
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
        events = self._events.get(trace_id) or self._load_events_from_store(trace_id)
        for event in events:
            lines.append(f"  - {event['event']}: {event.get('metadata', {})}")
        lines.append("spans:")
        spans = [span.to_dict() for span in self._spans.get(trace_id, [])] or self._load_spans_from_store(trace_id)
        for span in spans:
            lines.append(
                f"  - {span.get('span_type')}/{span.get('name')}: {span.get('status')}, "
                f"duration_ms={span.get('duration_ms')}, error={span.get('error')}"
            )
        return "\n".join(lines)

    def get_trace_record(self, trace_id: str) -> dict[str, Any] | None:
        record = self._records.get(trace_id) or self._load_record_from_store(trace_id)
        return record.to_dict() if record else None

    def get_trace_steps(self, trace_id: str) -> list[dict[str, Any]]:
        events = self._events.get(trace_id) or self._load_events_from_store(trace_id)
        spans = [span.to_dict() for span in self._spans.get(trace_id, [])] or self._load_spans_from_store(trace_id)
        steps: list[dict[str, Any]] = []
        for event in events:
            steps.append(
                {
                    "type": "event",
                    "timestamp": event.get("timestamp"),
                    "name": event.get("event"),
                    "metadata": event.get("metadata", {}),
                }
            )
        for span in spans:
            steps.append(
                {
                    "type": "span",
                    "timestamp": span.get("started_at"),
                    "name": span.get("name"),
                    "span_type": span.get("span_type"),
                    "status": span.get("status"),
                    "duration_ms": span.get("duration_ms"),
                    "input_preview": span.get("input_preview", {}),
                    "output_preview": span.get("output_preview", {}),
                    "error": span.get("error"),
                }
            )
        return sorted(steps, key=lambda step: step.get("timestamp") or "")

    def get_trace_tools(self, trace_id: str) -> list[dict[str, Any]]:
        return [
            step
            for step in self.get_trace_steps(trace_id)
            if step.get("span_type") == "tool" or str(step.get("name", "")).startswith("tool_call_")
        ]

    def get_trace_memory(self, trace_id: str) -> list[dict[str, Any]]:
        return [
            step
            for step in self.get_trace_steps(trace_id)
            if str(step.get("name", "")).startswith("memory_")
        ]

    def list_traces(self, *, limit: int = 20) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {trace_id: record.to_dict() for trace_id, record in self._records.items()}
        for entry in self.store.iter_events():
            event = entry.get("event")
            payload = entry.get("payload", {})
            trace_id = entry.get("trace_id")
            if not trace_id or event not in {"trace_started", "trace_finished"}:
                continue
            records[str(trace_id)] = payload
        ordered = sorted(
            records.values(),
            key=lambda record: record.get("ended_at") or record.get("started_at") or "",
            reverse=True,
        )
        return ordered[: max(limit, 1)]

    def tool_stats(self) -> dict[str, Any]:
        totals: dict[str, dict[str, Any]] = {}
        for entry in self.store.iter_events():
            if entry.get("event") != "tool_call_finished":
                continue
            metadata = entry.get("payload", {}).get("metadata", {})
            tool_name = str(metadata.get("tool_name") or "unknown")
            row = totals.setdefault(tool_name, {"tool_name": tool_name, "calls": 0, "successes": 0, "errors": 0, "total_duration_ms": 0})
            row["calls"] += 1
            if metadata.get("success"):
                row["successes"] += 1
            else:
                row["errors"] += 1
            row["total_duration_ms"] += int(metadata.get("duration_ms") or 0)
        for row in totals.values():
            row["avg_duration_ms"] = row["total_duration_ms"] / row["calls"] if row["calls"] else 0
        return {"tools": sorted(totals.values(), key=lambda row: row["calls"], reverse=True)}

    def _write(self, event: str, trace_id: str, payload: dict[str, Any]) -> None:
        self.store.append(
            {
                "timestamp": utc_now_iso(),
                "event": event,
                "trace_id": trace_id,
                "payload": redact_mapping(payload),
            }
        )

    def _load_record_from_store(self, trace_id: str) -> TraceRecord | None:
        record: TraceRecord | None = None
        for entry in self.store.iter_trace(trace_id):
            payload = entry.get("payload", {})
            if entry.get("event") == "trace_started":
                record = TraceRecord(**payload)
            elif entry.get("event") == "trace_finished":
                record = TraceRecord(**payload)
        if record:
            self._records[trace_id] = record
        return record

    def _load_events_from_store(self, trace_id: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for entry in self.store.iter_trace(trace_id):
            event = entry.get("event")
            payload = entry.get("payload", {})
            if event not in {"trace_started", "trace_finished", "span_started", "span_finished"}:
                events.append(payload)
        self._events[trace_id] = events
        return events

    def _load_spans_from_store(self, trace_id: str) -> list[dict[str, Any]]:
        spans: dict[str, dict[str, Any]] = {}
        for entry in self.store.iter_trace(trace_id):
            event = entry.get("event")
            payload = entry.get("payload", {})
            span_id = payload.get("span_id")
            if not span_id:
                continue
            if event == "span_started":
                spans[span_id] = payload
            elif event == "span_finished":
                spans[span_id] = {**spans.get(span_id, {}), **payload}
        return list(spans.values())


def _build_store(workspace: Path, store: str) -> JSONLTraceStore | SQLiteTraceStore:
    normalized = store.lower().strip()
    if normalized == "jsonl":
        return JSONLTraceStore(workspace=workspace)
    if normalized == "sqlite":
        return SQLiteTraceStore(workspace=workspace)
    raise ValueError(f"Unsupported trace store: {store}")
