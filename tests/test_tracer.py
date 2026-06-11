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
