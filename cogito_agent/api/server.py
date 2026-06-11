from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI
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


def create_app(config: AppConfig | None = None) -> FastAPI:
    runtime = build_default_runtime(config or load_config())
    app = FastAPI(title="Cogito-Agent Runtime")

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

    @app.post("/memory/optimize")
    async def optimize_memory() -> dict[str, Any]:
        result = runtime.memory_optimizer.run_once()
        return asdict(result)

    @app.get("/traces/{trace_id}")
    async def trace(trace_id: str) -> dict[str, Any]:
        return {"trace_id": trace_id, "summary": runtime.tracer.get_trace_summary(trace_id)}

    @app.post("/schedules")
    async def create_schedule(request: ScheduleRequest) -> dict[str, Any]:
        item = ScheduleItem(
            schedule_id=new_id("schedule"),
            name=request.name,
            prompt=request.prompt,
            trigger=request.trigger,  # type: ignore[arg-type]
            cron_expr=request.cron_expr,
            timezone=request.timezone,
        )
        runtime.schedule_store.add(item)
        return asdict(item)

    @app.get("/schedules")
    async def schedules() -> dict[str, Any]:
        return {"schedules": [asdict(item) for item in runtime.schedule_store.list()]}

    @app.get("/plugins")
    async def plugins() -> dict[str, Any]:
        return {"plugins": runtime.plugin_manager.list_plugins()}

    @app.get("/proactive/status")
    async def proactive_status() -> dict[str, Any]:
        return runtime.proactive_loop.status()

    @app.post("/proactive/tick")
    async def proactive_tick() -> dict[str, Any]:
        return asdict(runtime.proactive_loop.tick_once())

    @app.get("/drift/skills")
    async def drift_skills() -> dict[str, Any]:
        return runtime.drift_runner.status()

    @app.post("/drift/run")
    async def drift_run() -> dict[str, Any]:
        return asdict(runtime.drift_runner.run_once())

    return app


app = create_app()
