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


def test_dashboard_endpoint(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Cogito-Agent Dashboard" in response.text
    assert "Tools" in response.text
    assert "Memory" in response.text
    assert "Schedules" in response.text


def test_dashboard_data_and_health_endpoints(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    dashboard = client.get("/dashboard/data")
    health = client.get("/health")

    assert dashboard.status_code == 200
    assert dashboard.json()["metrics"]["tools"] > 0
    assert "tool_stats" in dashboard.json()
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_api_trace_subresources(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    chat = client.post("/chat", json={"message": "ping", "session_id": "trace-api"})
    trace_id = chat.json()["trace_id"]

    summary = client.get(f"/traces/{trace_id}")
    steps = client.get(f"/traces/{trace_id}/steps")
    tools = client.get(f"/traces/{trace_id}/tools")
    memory = client.get(f"/traces/{trace_id}/memory")

    assert summary.status_code == 200
    assert summary.json()["record"]["trace_id"] == trace_id
    assert steps.status_code == 200
    assert any(step["name"] == "user_input" for step in steps.json()["steps"])
    assert tools.status_code == 200
    assert tools.json()["tools"] == []
    assert memory.status_code == 200
    assert memory.json()["memory"] == []


def test_api_trace_list_and_tool_stats(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    chat = client.post("/chat", json={"message": "ping", "session_id": "trace-list"})
    trace_id = chat.json()["trace_id"]
    traces = client.get("/traces")
    stats = client.get("/traces/stats/tools")

    assert traces.status_code == 200
    assert traces.json()["traces"][0]["trace_id"] == trace_id
    assert stats.status_code == 200
    assert stats.json()["tools"] == []


def test_api_memory_delete(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    from cogito_agent.memory.markdown_store import MarkdownMemoryStore

    memory_store = MarkdownMemoryStore(tmp_path)
    memory_id = memory_store.add("User prefers Python.")

    response = client.delete(f"/memory/{memory_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert memory_id not in client.get("/memory").text


def test_api_schedule_update_and_cancel(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    created = client.post("/schedules", json={"name": "demo", "prompt": "ping", "trigger": "once"})
    schedule_id = created.json()["schedule_id"]

    updated = client.patch(f"/schedules/{schedule_id}", json={"name": "renamed", "enabled": True})
    fetched = client.get(f"/schedules/{schedule_id}")
    cancelled = client.delete(f"/schedules/{schedule_id}")

    assert updated.status_code == 200
    assert updated.json()["name"] == "renamed"
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "renamed"
    assert cancelled.status_code == 200
    assert cancelled.json()["schedule"]["enabled"] is False


def test_api_due_schedules_and_proactive_outbox(tmp_path):
    config = AppConfig(workspace=tmp_path)
    config.proactive.enabled = True
    config.proactive.cooldown_seconds = 0
    app = create_app(config)
    client = TestClient(app)

    created = client.post("/schedules", json={"name": "demo", "prompt": "ping", "trigger": "once"})
    due = client.get("/schedules/due")
    tick = client.post("/proactive/tick")
    outbox = client.get("/proactive/outbox")

    assert created.status_code == 200
    assert due.status_code == 200
    assert due.json()["schedules"][0]["name"] == "demo"
    assert tick.status_code == 200
    assert tick.json()["should_send"] is True
    assert outbox.status_code == 200
    assert outbox.json()["messages"][0]["title"] == "demo"


def test_api_prompt_management(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    current = client.get("/prompts/system")
    updated = client.put("/prompts/system", json={"content": "You are a test agent.", "reason": "test"})
    history = client.get("/prompts/system/history")

    assert current.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["metadata"]["reason"] == "test"
    assert history.status_code == 200
    assert history.json()["versions"][0]["content"] == "You are a test agent."


def test_api_drift_skill_management(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    created = client.put("/drift/skills/custom-skill", json={"description": "Custom", "body": "## Goal\nDo work"})
    fetched = client.get("/drift/skills/custom-skill")
    deleted = client.delete("/drift/skills/custom-skill")

    assert created.status_code == 200
    assert created.json()["name"] == "custom-skill"
    assert fetched.status_code == 200
    assert fetched.json()["description"] == "Custom"
    assert deleted.status_code == 200


def test_api_proactive_config_update(tmp_path):
    config = AppConfig(workspace=tmp_path)
    app = create_app(config)
    client = TestClient(app)

    response = client.patch(
        "/proactive/config",
        json={"enabled": True, "threshold": 0.9, "daily_limit": 1, "cooldown_seconds": 5, "quiet_hours": "23:00-06:00"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["threshold"] == 0.9
    assert data["quota"]["daily_limit"] == 1
    assert data["quota"]["cooldown_seconds"] == 5
    assert data["quota"]["quiet_hours"] == "23:00-06:00"
