from __future__ import annotations

from dataclasses import asdict
from html import escape
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from cogito_agent.agent.state import InboundMessage, new_id
from cogito_agent.cli.app import build_default_runtime
from cogito_agent.config import AppConfig, load_config
from cogito_agent.tools.schedule import ScheduleItem


class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str
    channel: str = "api"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScheduleRequest(BaseModel):
    name: str
    prompt: str
    trigger: str = "once"
    cron_expr: str | None = None
    timezone: str = "Asia/Shanghai"
    channel: str = "api"


class ScheduleUpdateRequest(BaseModel):
    name: str | None = None
    prompt: str | None = None
    trigger: str | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    channel: str | None = None
    enabled: bool | None = None


def create_app(config: AppConfig | None = None) -> FastAPI:
    runtime = build_default_runtime(config or load_config())
    app = FastAPI(title="Cogito-Agent Runtime")

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard() -> str:
        tools = runtime.tool_registry.list_tools()
        memories = runtime.memory_store.list_entries()
        schedules = runtime.schedule_store.list()
        traces = runtime.tracer.list_traces(limit=10)
        tool_stats = runtime.tracer.tool_stats()["tools"]
        last_trace_id = runtime.tracer.last_trace_id
        rows = "\n".join(
            f"<tr><td>{escape(item.schedule_id)}</td><td>{escape(item.name)}</td><td>{escape(item.trigger)}</td><td>{item.enabled}</td></tr>"
            for item in schedules
        )
        memory_rows = "\n".join(
            f"<tr><td>{escape(memory.memory_id)}</td><td>{escape(memory.content_preview)}</td><td>{memory.score:.3f}</td></tr>"
            for memory in memories
        )
        tool_rows = "\n".join(
            f"<tr><td>{escape(tool.name)}</td><td>{escape(tool.risk_level)}</td><td>{tool.enabled}</td></tr>"
            for tool in tools
        )
        trace_rows = "\n".join(
            f"<tr><td><a href=\"/traces/{escape(trace['trace_id'])}\">{escape(trace['trace_id'])}</a></td>"
            f"<td>{escape(trace.get('session_id') or '')}</td><td>{escape(trace.get('status') or '')}</td>"
            f"<td>{trace.get('duration_ms') or ''}</td><td>{escape(trace.get('user_message_preview') or '')}</td></tr>"
            for trace in traces
        )
        tool_stat_rows = "\n".join(
            f"<tr><td>{escape(row['tool_name'])}</td><td>{row['calls']}</td><td>{row['successes']}</td>"
            f"<td>{row['errors']}</td><td>{row['avg_duration_ms']:.1f}</td></tr>"
            for row in tool_stats
        )
        trace_link = f'<a href="/traces/{escape(last_trace_id)}">{escape(last_trace_id)}</a>' if last_trace_id else "No trace yet"
        return f"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Cogito-Agent Dashboard</title>
          <style>
            body {{ font-family: system-ui, sans-serif; margin: 32px; color: #172033; background: #f7f8fb; }}
            main {{ max-width: 1080px; margin: 0 auto; }}
            section {{ background: white; border: 1px solid #d9deea; border-radius: 8px; padding: 16px; margin: 16px 0; }}
            h1, h2 {{ margin: 0 0 12px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
            th, td {{ text-align: left; border-bottom: 1px solid #edf0f6; padding: 8px; vertical-align: top; }}
            .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
            .metric {{ background: white; border: 1px solid #d9deea; border-radius: 8px; padding: 16px; }}
            .value {{ font-size: 28px; font-weight: 700; }}
          </style>
        </head>
        <body>
          <main>
            <h1>Cogito-Agent Dashboard</h1>
            <div class="metrics">
              <div class="metric"><div>Tools</div><div class="value">{len(tools)}</div></div>
              <div class="metric"><div>Memories</div><div class="value">{len(memories)}</div></div>
              <div class="metric"><div>Schedules</div><div class="value">{len(schedules)}</div></div>
              <div class="metric"><div>Traces</div><div class="value">{len(traces)}</div></div>
              <div class="metric"><div>Last trace</div><div>{trace_link}</div></div>
            </div>
            <section>
              <h2>Trace Timeline</h2>
              <table><thead><tr><th>ID</th><th>Session</th><th>Status</th><th>Duration</th><th>Input</th></tr></thead><tbody>{trace_rows}</tbody></table>
            </section>
            <section>
              <h2>Tool Stats</h2>
              <table><thead><tr><th>Name</th><th>Calls</th><th>Successes</th><th>Errors</th><th>Avg ms</th></tr></thead><tbody>{tool_stat_rows}</tbody></table>
            </section>
            <section>
              <h2>Tools</h2>
              <table><thead><tr><th>Name</th><th>Risk</th><th>Enabled</th></tr></thead><tbody>{tool_rows}</tbody></table>
            </section>
            <section>
              <h2>Memory</h2>
              <table><thead><tr><th>ID</th><th>Preview</th><th>Score</th></tr></thead><tbody>{memory_rows}</tbody></table>
            </section>
            <section>
              <h2>Schedules</h2>
              <table><thead><tr><th>ID</th><th>Name</th><th>Trigger</th><th>Enabled</th></tr></thead><tbody>{rows}</tbody></table>
            </section>
          </main>
        </body>
        </html>
        """

    @app.post("/chat")
    async def chat(request: ChatRequest) -> dict[str, Any]:
        inbound = InboundMessage(
            message_id=new_id("api_msg"),
            session_id=request.session_id,
            channel=request.channel,
            user_id=None,
            content=request.message,
            metadata=request.metadata,
        )
        response = await runtime.agent.process(inbound)
        return asdict(response)

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "messages": [asdict(message) for message in runtime.session_manager.history(session_id)]}

    @app.post("/sessions/{session_id}/reset")
    async def reset_session(session_id: str) -> dict[str, Any]:
        runtime.session_manager.reset(session_id)
        return {"session_id": session_id, "status": "reset"}

    @app.get("/tools")
    async def tools() -> dict[str, Any]:
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "risk_level": tool.risk_level,
                    "enabled": tool.enabled,
                }
                for tool in runtime.tool_registry.list_tools()
            ]
        }

    @app.get("/memory")
    async def memory() -> dict[str, Any]:
        return {"memories": [asdict(hit) for hit in runtime.memory_store.list_entries()]}

    @app.delete("/memory/{memory_id}")
    async def forget_memory(memory_id: str) -> dict[str, Any]:
        if not runtime.memory_store.forget(memory_id):
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"memory_id": memory_id, "status": "deleted"}

    @app.post("/memory/optimize")
    async def optimize_memory() -> dict[str, Any]:
        result = runtime.memory_optimizer.run_once()
        return asdict(result)

    @app.get("/traces")
    async def traces(limit: int = 20) -> dict[str, Any]:
        return {"traces": runtime.tracer.list_traces(limit=limit)}

    @app.get("/traces/stats/tools")
    async def trace_tool_stats() -> dict[str, Any]:
        return runtime.tracer.tool_stats()

    @app.get("/traces/{trace_id}")
    async def trace(trace_id: str) -> dict[str, Any]:
        record = runtime.tracer.get_trace_record(trace_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        return {"trace_id": trace_id, "record": record, "summary": runtime.tracer.get_trace_summary(trace_id)}

    @app.get("/traces/{trace_id}/steps")
    async def trace_steps(trace_id: str) -> dict[str, Any]:
        if runtime.tracer.get_trace_record(trace_id) is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        return {"trace_id": trace_id, "steps": runtime.tracer.get_trace_steps(trace_id)}

    @app.get("/traces/{trace_id}/tools")
    async def trace_tools(trace_id: str) -> dict[str, Any]:
        if runtime.tracer.get_trace_record(trace_id) is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        return {"trace_id": trace_id, "tools": runtime.tracer.get_trace_tools(trace_id)}

    @app.get("/traces/{trace_id}/memory")
    async def trace_memory(trace_id: str) -> dict[str, Any]:
        if runtime.tracer.get_trace_record(trace_id) is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        return {"trace_id": trace_id, "memory": runtime.tracer.get_trace_memory(trace_id)}

    @app.post("/schedules")
    async def create_schedule(request: ScheduleRequest) -> dict[str, Any]:
        item = ScheduleItem(
            schedule_id=new_id("schedule"),
            name=request.name,
            prompt=request.prompt,
            trigger=request.trigger,  # type: ignore[arg-type]
            cron_expr=request.cron_expr,
            timezone=request.timezone,
            channel=request.channel,
        )
        runtime.schedule_store.add(item)
        return asdict(item)

    @app.get("/schedules")
    async def schedules() -> dict[str, Any]:
        return {"schedules": [asdict(item) for item in runtime.schedule_store.list()]}

    @app.get("/schedules/due")
    async def due_schedules() -> dict[str, Any]:
        return {"schedules": [asdict(item) for item in runtime.schedule_store.due()]}

    @app.get("/schedules/{schedule_id}")
    async def get_schedule(schedule_id: str) -> dict[str, Any]:
        item = runtime.schedule_store.get(schedule_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return asdict(item)

    @app.patch("/schedules/{schedule_id}")
    async def update_schedule(schedule_id: str, request: ScheduleUpdateRequest) -> dict[str, Any]:
        item = runtime.schedule_store.update(schedule_id, **request.model_dump(exclude_unset=True))
        if item is None:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return asdict(item)

    @app.delete("/schedules/{schedule_id}")
    async def cancel_schedule(schedule_id: str) -> dict[str, Any]:
        if not runtime.schedule_store.cancel(schedule_id):
            raise HTTPException(status_code=404, detail="Schedule not found")
        item = runtime.schedule_store.get(schedule_id)
        return {"schedule_id": schedule_id, "status": "cancelled", "schedule": asdict(item) if item else None}

    @app.get("/plugins")
    async def plugins() -> dict[str, Any]:
        return {"plugins": runtime.plugin_manager.list_plugins()}

    @app.get("/proactive/status")
    async def proactive_status() -> dict[str, Any]:
        return runtime.proactive_loop.status()

    @app.post("/proactive/tick")
    async def proactive_tick() -> dict[str, Any]:
        return asdict(runtime.proactive_loop.tick_once())

    @app.get("/proactive/outbox")
    async def proactive_outbox() -> dict[str, Any]:
        return {"messages": [asdict(message) for message in runtime.proactive_loop.push_store.list()]}

    @app.get("/drift/skills")
    async def drift_skills() -> dict[str, Any]:
        return runtime.drift_runner.status()

    @app.post("/drift/run")
    async def drift_run() -> dict[str, Any]:
        return asdict(runtime.drift_runner.run_once(force=True))

    return app


app = create_app()
