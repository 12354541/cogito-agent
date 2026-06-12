from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cogito_agent.agent.state import new_id, utc_now_iso


@dataclass(slots=True)
class PromptSnapshot:
    version_id: str
    content_hash: str
    content: str
    created_at: str
    metadata: dict[str, Any]


class PromptStore:
    def __init__(self, workspace: Path, default_prompt_path: Path) -> None:
        self.prompt_dir = workspace / "prompts"
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        self.current_path = self.prompt_dir / "system_prompt.md"
        self.history_path = self.prompt_dir / "system_prompt_history.jsonl"
        if not self.current_path.exists():
            self.current_path.write_text(default_prompt_path.read_text(encoding="utf-8"), encoding="utf-8")
            self._append_history(self.current_path.read_text(encoding="utf-8"), metadata={"source": "initial"})

    def get_current(self) -> PromptSnapshot:
        content = self.current_path.read_text(encoding="utf-8")
        return PromptSnapshot(
            version_id="current",
            content_hash=_hash(content),
            content=content,
            created_at=utc_now_iso(),
            metadata={"path": str(self.current_path)},
        )

    def update(self, content: str, *, metadata: dict[str, Any] | None = None) -> PromptSnapshot:
        previous = self.current_path.read_text(encoding="utf-8") if self.current_path.exists() else ""
        self.current_path.write_text(content, encoding="utf-8")
        return self._append_history(content, metadata={**(metadata or {}), "previous_hash": _hash(previous)})

    def history(self, *, limit: int = 20) -> list[PromptSnapshot]:
        if not self.history_path.exists():
            return []
        snapshots: list[PromptSnapshot] = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            snapshots.append(PromptSnapshot(**data))
        return list(reversed(snapshots))[: max(limit, 1)]

    def _append_history(self, content: str, *, metadata: dict[str, Any]) -> PromptSnapshot:
        snapshot = PromptSnapshot(
            version_id=new_id("prompt"),
            content_hash=_hash(content),
            content=content,
            created_at=utc_now_iso(),
            metadata=metadata,
        )
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_snapshot_to_dict(snapshot), ensure_ascii=False) + "\n")
        return snapshot


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _snapshot_to_dict(snapshot: PromptSnapshot) -> dict[str, Any]:
    return {
        "version_id": snapshot.version_id,
        "content_hash": snapshot.content_hash,
        "content": snapshot.content,
        "created_at": snapshot.created_at,
        "metadata": snapshot.metadata,
    }
