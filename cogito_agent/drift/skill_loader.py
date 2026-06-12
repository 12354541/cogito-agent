from __future__ import annotations

import re
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

    def get_skill(self, name: str) -> DriftSkill | None:
        safe_name = _safe_name(name)
        path = self.skills_dir / safe_name / "SKILL.md"
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_front_matter(text)
        return DriftSkill(
            name=metadata.get("name") or safe_name,
            description=metadata.get("description") or "",
            path=path.parent,
            body=body,
            metadata=metadata,
        )

    def upsert_skill(self, *, name: str, description: str, body: str) -> DriftSkill:
        safe_name = _safe_name(name)
        skill_dir = self.skills_dir / safe_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"""---
name: {safe_name}
description: {description}
---

{body.strip()}
""",
            encoding="utf-8",
        )
        skill = self.get_skill(safe_name)
        if skill is None:
            raise RuntimeError(f"Failed to write skill: {safe_name}")
        return skill

    def delete_skill(self, name: str) -> bool:
        safe_name = _safe_name(name)
        skill_path = self.skills_dir / safe_name / "SKILL.md"
        if not skill_path.exists():
            return False
        skill_path.unlink()
        return True

    def ensure_builtin_skills(self) -> None:
        self._ensure_skill(
            name="audit-dirty-memories",
            description="Audit pending and long-term memory files for obvious issues.",
            body="Check memory files and write a lightweight audit note.",
        )
        self._ensure_skill(
            name="self-diagnosis",
            description="Check runtime background task health and append a diagnosis note.",
            body="Review prompt, memory, tool loop, and background-task health.",
        )

    def _ensure_skill(self, *, name: str, description: str, body: str) -> None:
        skill_dir = self.skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            skill_path.write_text(
                f"""---
name: {name}
description: {description}
---

## Goal

{body}
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


def _safe_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("Skill name may only contain letters, numbers, dot, underscore, and dash.")
    return name
