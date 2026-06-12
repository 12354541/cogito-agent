from __future__ import annotations

from cogito_agent.tracing.tracer import Tracer


def test_tracer_records_last_trace_summary(tmp_path):
    tracer = Tracer(workspace=tmp_path)
    trace = tracer.start_trace(
        session_id="default",
        user_message_preview="你好",
        metadata={"api_key": "secret"},
    )
    tracer.record_event(trace, event="user_input", metadata={"preview": "你好"})
    tracer.finish_trace(trace, status="ok", final_response_preview="我收到了你的消息：你好")

    summary = tracer.get_last_trace_summary()
    assert "trace_id:" in summary
    assert "status: ok" in summary
    assert "user_input: 你好" in summary

    trace_file = next((tmp_path / "traces").glob("*.jsonl"))
    assert "secret" not in trace_file.read_text(encoding="utf-8")
    assert "[REDACTED]" in trace_file.read_text(encoding="utf-8")


def test_tracer_loads_structured_trace_from_jsonl(tmp_path):
    tracer = Tracer(workspace=tmp_path)
    trace = tracer.start_trace(session_id="default", user_message_preview="hello")
    span = tracer.start_span(trace, span_type="tool", name="calculator", input_preview={"expression": "1+1"})
    tracer.end_span(trace, span, status="ok", output_preview={"content": "2"})
    tracer.finish_trace(trace, status="ok", final_response_preview="done")

    reloaded = Tracer(workspace=tmp_path)

    record = reloaded.get_trace_record(trace.trace_id)
    tools = reloaded.get_trace_tools(trace.trace_id)

    assert record is not None
    assert record["trace_id"] == trace.trace_id
    assert record["status"] == "ok"
    assert tools[0]["name"] == "calculator"
    assert tools[0]["output_preview"]["content"] == "2"


def test_tracer_can_use_sqlite_store(tmp_path):
    tracer = Tracer(workspace=tmp_path, store="sqlite")
    trace = tracer.start_trace(session_id="default", user_message_preview="hello sqlite")
    tracer.record_event(trace, event="memory_retrieval_started", metadata={"top_k": 3})
    tracer.finish_trace(trace, status="ok", final_response_preview="done")

    reloaded = Tracer(workspace=tmp_path, store="sqlite")

    record = reloaded.get_trace_record(trace.trace_id)
    memory_steps = reloaded.get_trace_memory(trace.trace_id)

    assert (tmp_path / "traces.sqlite3").exists()
    assert record is not None
    assert record["user_message_preview"] == "hello sqlite"
    assert memory_steps[0]["name"] == "memory_retrieval_started"
    assert memory_steps[0]["metadata"]["top_k"] == 3


def test_tracer_lists_traces_and_tool_stats(tmp_path):
    tracer = Tracer(workspace=tmp_path)
    trace = tracer.start_trace(session_id="default", user_message_preview="tool run")
    tracer.record_event(trace, event="tool_call_finished", metadata={"tool_name": "calculator", "success": True, "duration_ms": 12})
    tracer.finish_trace(trace, status="ok", final_response_preview="done")

    traces = tracer.list_traces()
    stats = tracer.tool_stats()

    assert traces[0]["trace_id"] == trace.trace_id
    assert traces[0]["status"] == "ok"
    assert stats["tools"][0]["tool_name"] == "calculator"
    assert stats["tools"][0]["calls"] == 1
    assert stats["tools"][0]["successes"] == 1


def test_tracer_opentelemetry_exporter_is_optional(tmp_path):
    tracer = Tracer(workspace=tmp_path, otel_enabled=True, otel_service_name="test-service")
    trace = tracer.start_trace(session_id="default", user_message_preview="otel")
    span = tracer.start_span(trace, span_type="reasoner", name="test")

    tracer.end_span(trace, span, status="ok")
    tracer.finish_trace(trace, status="ok", final_response_preview="done")

    assert tracer.get_trace_record(trace.trace_id)["status"] == "ok"  # type: ignore[index]
