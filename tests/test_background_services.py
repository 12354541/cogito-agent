from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cogito_agent.drift.runner import DriftRunner
from cogito_agent.proactive.loop import ProactiveLoop
from cogito_agent.proactive.quota import ProactiveQuota
from cogito_agent.tools.schedule import ScheduleItem, ScheduleStore


def test_schedule_store_add_cancel(tmp_path):
    store = ScheduleStore(tmp_path)
    item = ScheduleItem(schedule_id="schedule_test", name="demo", trigger="once", prompt="ping")

    store.add(item)

    assert store.list()[0].name == "demo"
    assert store.cancel("schedule_test") is True
    assert store.list()[0].enabled is False


def test_schedule_store_due_and_mark_triggered(tmp_path):
    store = ScheduleStore(tmp_path)
    now = datetime.now(timezone.utc)
    item = ScheduleItem(
        schedule_id="schedule_due",
        name="demo",
        trigger="once",
        prompt="ping",
        cron_expr=(now - timedelta(minutes=1)).isoformat(),
    )
    store.add(item)

    due = store.due(now)
    updated = store.mark_triggered("schedule_due", now)

    assert due[0].schedule_id == "schedule_due"
    assert updated is not None
    assert updated.enabled is False
    assert store.due(now) == []


def test_schedule_store_cron_uses_timezone(tmp_path):
    store = ScheduleStore(tmp_path)
    now = datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc)
    store.add(
        ScheduleItem(
            schedule_id="schedule_tz",
            name="daily",
            trigger="cron",
            prompt="ping",
            cron_expr="10:00",
            timezone="Asia/Shanghai",
        )
    )

    due = store.due(now)

    assert due[0].schedule_id == "schedule_tz"


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


def test_proactive_tick_writes_outbox_and_triggers_schedule(tmp_path):
    schedule_store = ScheduleStore(tmp_path)
    now = datetime.now(timezone.utc)
    schedule_store.add(
        ScheduleItem(
            schedule_id="schedule_alert",
            name="Reminder",
            trigger="once",
            prompt="Check this",
            cron_expr=(now - timedelta(minutes=1)).isoformat(),
        )
    )
    loop = ProactiveLoop(
        tmp_path,
        schedule_store=schedule_store,
        quota=ProactiveQuota(tmp_path, cooldown_seconds=0),
    )

    decision = loop.tick_once()

    assert decision.should_send is True
    assert decision.metadata["message_id"].startswith("push_")
    assert loop.status()["outbox_count"] == 1
    assert schedule_store.get("schedule_alert").enabled is False  # type: ignore[union-attr]


def test_drift_runner_creates_audit(tmp_path):
    runner = DriftRunner(tmp_path)

    result = runner.run_once()

    assert result.status == "ok"
    assert result.skill_name == "audit-dirty-memories"
    assert (tmp_path / "drift" / "skills" / "audit-dirty-memories" / "audited.md").exists()


def test_drift_runner_enforces_interval_and_force(tmp_path):
    runner = DriftRunner(tmp_path, min_interval_hours=1)

    first = runner.run_once()
    second = runner.run_once()
    forced = runner.run_once(force=True)

    assert first.status == "ok"
    assert second.status == "skipped"
    assert second.details["reason"] == "min_interval"
    assert second.details["finish_drift"] is True
    assert forced.status == "ok"
    assert forced.details["finish_drift"] is True


def test_drift_runner_executes_generic_skill(tmp_path):
    runner = DriftRunner(tmp_path)
    runner.loader.upsert_skill(name="custom", description="Custom skill", body="## Goal\nDo a generic task")

    result = runner.run_once(force=True)

    # Built-ins sort first on some file systems, so run custom directly by
    # removing built-in interval pressure through a second forced run if needed.
    if result.skill_name != "custom":
        (tmp_path / "drift" / "skills" / "audit-dirty-memories" / "SKILL.md").unlink()
        (tmp_path / "drift" / "skills" / "self-diagnosis" / "SKILL.md").unlink()
        result = runner.run_once(force=True)

    assert result.status == "ok"
    assert result.skill_name == "custom"
    assert result.details["generic"] is True
    assert (tmp_path / "drift" / "skills" / "custom" / "runs.md").exists()
