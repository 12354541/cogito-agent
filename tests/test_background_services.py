from __future__ import annotations

from cogito_agent.drift.runner import DriftRunner
from cogito_agent.proactive.loop import ProactiveLoop
from cogito_agent.tools.schedule import ScheduleItem, ScheduleStore


def test_schedule_store_add_cancel(tmp_path):
    store = ScheduleStore(tmp_path)
    item = ScheduleItem(schedule_id="schedule_test", name="demo", trigger="once", prompt="ping")

    store.add(item)

    assert store.list()[0].name == "demo"
    assert store.cancel("schedule_test") is True
    assert store.list()[0].enabled is False


def test_proactive_tick_selects_alert(tmp_path):
    (tmp_path / "proactive_sources.json").write_text(
        '[{"item_id":"a1","channel":"alert","title":"Important","body":"Check now","priority":5}]',
        encoding="utf-8",
    )
    loop = ProactiveLoop(tmp_path)

    decision = loop.tick_once()

    assert decision.should_send is True
    assert decision.item is not None
    assert decision.item.item_id == "a1"


def test_drift_runner_creates_audit(tmp_path):
    runner = DriftRunner(tmp_path)

    result = runner.run_once()

    assert result.status == "ok"
    assert result.skill_name == "audit-dirty-memories"
    assert (tmp_path / "drift" / "skills" / "audit-dirty-memories" / "audited.md").exists()
