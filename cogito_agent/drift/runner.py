from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cogito_agent.agent.state import utc_now_iso
from cogito_agent.drift.models import DriftRunResult, DriftSkill
from cogito_agent.drift.skill_loader import SkillLoader
from cogito_agent.tracing.tracer import Tracer


class DriftRunner:
    def __init__(
        self,
        workspace: Path,
        loader: SkillLoader | None = None,
        *,
        tracer: Tracer | None = None,
        enabled: bool = True,
        min_interval_hours: float = 1.0,
        max_steps: int = 30,
    ) -> None:
        self.workspace = workspace
        self.loader = loader or SkillLoader(workspace)
        self.tracer = tracer
        self.enabled = enabled
        self.min_interval_hours = min_interval_hours
        self.max_steps = max_steps
        self.state_path = workspace / "drift" / "state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self.state_path.write_text("{}", encoding="utf-8")
        self.loader.ensure_builtin_skills()

    def list_skills(self) -> list[DriftSkill]:
        return self.loader.scan_skills()

    def run_once(self, *, force: bool = False) -> DriftRunResult:
        if not self.enabled and not force:
            return DriftRunResult(skill_name=None, status="skipped", details={"reason": "disabled", "finish_drift": True})
        if not force and not self._interval_elapsed():
            return DriftRunResult(skill_name=None, status="skipped", details={"reason": "min_interval", "finish_drift": True})
        trace = (
            self.tracer.start_trace(session_id="drift", user_message_preview="drift_run", metadata={"channel": "drift"})
            if self.tracer
            else None
        )
        skills = self.list_skills()
        if not skills:
            return self._finish(trace, DriftRunResult(skill_name=None, status="skipped", details={"reason": "no_skills"}))
        skill = skills[0]
        if skill.name == "audit-dirty-memories":
            return self._finish(trace, self._audit_dirty_memories(skill))
        if skill.name == "self-diagnosis":
            return self._finish(trace, self._self_diagnosis(skill))
        return self._finish(trace, DriftRunResult(skill_name=skill.name, status="skipped", details={"reason": "unsupported_skill"}))

    def _audit_dirty_memories(self, skill: DriftSkill) -> DriftRunResult:
        memory_dir = self.workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        pending_path = memory_dir / "PENDING.md"
        memory_path = memory_dir / "MEMORY.md"
        audited_path = skill.path / "audited.md"
        pending_lines = pending_path.read_text(encoding="utf-8", errors="ignore").splitlines() if pending_path.exists() else []
        memory_lines = memory_path.read_text(encoding="utf-8", errors="ignore").splitlines() if memory_path.exists() else []
        note = (
            f"- audited_at: {utc_now_iso()} | "
            f"pending_lines: {len(pending_lines)} | memory_lines: {len(memory_lines)}\n"
        )
        with audited_path.open("a", encoding="utf-8") as f:
            f.write(note)
        return DriftRunResult(
            skill_name=skill.name,
            status="ok",
            message_result="silent",
            details={"audited_path": str(audited_path), "pending_lines": len(pending_lines), "memory_lines": len(memory_lines)},
        )

    def _self_diagnosis(self, skill: DriftSkill) -> DriftRunResult:
        report_path = skill.path / "diagnosis.md"
        note = f"- checked_at: {utc_now_iso()} | max_steps: {self.max_steps}\n"
        with report_path.open("a", encoding="utf-8") as f:
            f.write(note)
        return DriftRunResult(
            skill_name=skill.name,
            status="ok",
            message_result="silent",
            details={"report_path": str(report_path)},
        )

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "min_interval_hours": self.min_interval_hours,
            "max_steps": self.max_steps,
            "state": self._state(),
            "skills": [{"name": skill.name, "description": skill.description} for skill in self.list_skills()],
        }

    def _finish(self, trace, result: DriftRunResult) -> DriftRunResult:
        result.details = {**result.details, "finish_drift": True}
        self._mark_run()
        if trace and self.tracer:
            self.tracer.record_event(
                trace,
                event="drift_finished",
                metadata={"skill_name": result.skill_name, "status": result.status, "details": result.details},
            )
            self.tracer.finish_trace(trace, status=result.status, final_response_preview=str(result.skill_name))
            result.details = {**result.details, "trace_id": trace.trace_id}
        return result

    def _interval_elapsed(self) -> bool:
        last_run_at = _parse_dt(self._state().get("last_run_at"))
        if last_run_at is None:
            return True
        return datetime.now(timezone.utc) - last_run_at >= timedelta(hours=self.min_interval_hours)

    def _mark_run(self) -> None:
        state = self._state()
        state["last_run_at"] = utc_now_iso()
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _state(self) -> dict[str, object]:
        return json.loads(self.state_path.read_text(encoding="utf-8") or "{}")


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
