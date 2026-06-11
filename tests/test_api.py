from __future__ import annotations

from fastapi.testclient import TestClient

from cogito_agent.api.server import create_app
from cogito_agent.config import AppConfig


def test_chat_api_returns_trace_id(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    response = client.post("/chat", json={"message": "你好", "session_id": "api-test"})

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "我收到了你的消息：你好"
    assert data["trace_id"].startswith("trace_")


def test_api_background_endpoints(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    schedule = client.post("/schedules", json={"name": "demo", "prompt": "ping", "trigger": "once"})
    plugins = client.get("/plugins")
    drift = client.post("/drift/run")

    assert schedule.status_code == 200
    assert schedule.json()["name"] == "demo"
    assert plugins.status_code == 200
    assert any(plugin["name"] == "tool_loop_guard" for plugin in plugins.json()["plugins"])
    assert drift.status_code == 200
    assert drift.json()["status"] == "ok"
