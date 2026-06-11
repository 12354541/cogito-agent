from __future__ import annotations

from pathlib import Path

from cogito_agent.drift.models import DriftSkill


class SkillLoader:
    def __init__(self, workspace: Path) -> None:
        self.skills_dir = workspace / "drift" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def scan_skills(self) -> list[DriftSkill]:
        skills: list[DriftSkill] = []
        for path in self.skills_dir.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            metadata, body = _parse_front_matter(text)
            skills.append(
                DriftSkill(
                    name=metadata.get("name") or path.parent.name,
                    description=metadata.get("description") or "",
                    path=path.parent,
                    body=body,
                    metadata=metadata,
                )
            )
        return skills

    def ensure_builtin_skills(self) -> None:
        skill_dir = self.skills_dir / "audit-dirty-memories"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            skill_path.write_text(
                """---
name: audit-dirty-memories
description: Audit pending and long-term memory files for obvious issues.
---

## Goal

Check memory files and write a lightweight audit note.
""",
                encoding="utf-8",
            )


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, parts[2].strip()
