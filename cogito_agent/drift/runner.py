from __future__ import annotations

from pathlib import Path

from cogito_agent.agent.state import utc_now_iso
from cogito_agent.drift.models import DriftRunResult, DriftSkill
from cogito_agent.drift.skill_loader import SkillLoader


class DriftRunner:
    def __init__(self, workspace: Path, loader: SkillLoader | None = None) -> None:
        self.workspace = workspace
        self.loader = loader or SkillLoader(workspace)
        self.loader.ensure_builtin_skills()

    def list_skills(self) -> list[DriftSkill]:
        return self.loader.scan_skills()

    def run_once(self) -> DriftRunResult:
        skills = self.list_skills()
        if not skills:
            return DriftRunResult(skill_name=None, status="skipped", details={"reason": "no_skills"})
        skill = skills[0]
        if skill.name == "audit-dirty-memories":
            return self._audit_dirty_memories(skill)
        return DriftRunResult(skill_name=skill.name, status="skipped", details={"reason": "unsupported_skill"})

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

    def status(self) -> dict[str, object]:
        return {"enabled": True, "skills": [{"name": skill.name, "description": skill.description} for skill in self.list_skills()]}
