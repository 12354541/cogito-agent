from __future__ import annotations

import re
from pathlib import Path

from cogito_agent.agent.state import utc_now_iso
from cogito_agent.memory.markdown_store import MarkdownMemoryStore


class MemoryConsolidator:
    def __init__(self, workspace: Path, memory_store: MarkdownMemoryStore) -> None:
        self.workspace = workspace
        self.memory_store = memory_store
        self.memory_dir = workspace / "memory"
        self.pending_path = self.memory_dir / "PENDING.md"
        self.history_path = self.memory_dir / "HISTORY.md"
        self.recent_context_path = self.memory_dir / "RECENT_CONTEXT.md"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.pending_path, "# Pending Memory\n\n")
        self._ensure_file(self.history_path, "# Memory History\n\n")
        self._ensure_file(self.recent_context_path, "# Recent Context\n\n")

    def maybe_enqueue_user_message(self, content: str, *, trace_id: str) -> bool:
        self.record_recent_context(content, trace_id=trace_id)
        markers = ("记住", "请记住", "remember", "更正", "纠正", "correct")
        lowered = content.lower()
        if not any(marker in lowered for marker in markers):
            return False
        cleaned = _strip_memory_prefix(content)
        with self.pending_path.open("a", encoding="utf-8") as f:
            f.write(f"- created_at: {utc_now_iso()} | source_trace_id: {trace_id} | {cleaned}\n")
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(f"- pending_at: {utc_now_iso()} | source_trace_id: {trace_id} | {cleaned}\n")
        return True

    def promote_pending(self, *, source_trace_id: str | None = None) -> list[str]:
        lines = self.pending_path.read_text(encoding="utf-8").splitlines()
        kept: list[str] = []
        promoted: list[str] = []
        for line in lines:
            if not line.startswith("- "):
                kept.append(line)
                continue
            pending_trace_id = _extract_field(line, "source_trace_id")
            content = line.split("|")[-1].strip()
            if not content:
                continue
            effective_trace_id = source_trace_id or pending_trace_id
            memory_id = self.memory_store.add(
                content,
                source_trace_id=effective_trace_id,
                source_ref=effective_trace_id,
                confidence=0.7,
                metadata={"source": "pending"},
            )
            promoted.append(memory_id)
            with self.history_path.open("a", encoding="utf-8") as f:
                f.write(f"- promoted_at: {utc_now_iso()} | memory_id: {memory_id} | source_trace_id: {effective_trace_id or ''} | {content}\n")
        self.pending_path.write_text("\n".join(kept).strip() + "\n\n", encoding="utf-8")
        return promoted

    def record_recent_context(self, content: str, *, trace_id: str, max_lines: int = 80) -> None:
        existing = self.recent_context_path.read_text(encoding="utf-8").splitlines()
        body = [line for line in existing if line.startswith("- ")]
        body.append(f"- seen_at: {utc_now_iso()} | source_trace_id: {trace_id} | {content[:500]}")
        self.recent_context_path.write_text("\n".join(["# Recent Context", "", *body[-max_lines:]]) + "\n", encoding="utf-8")

    @staticmethod
    def _ensure_file(path: Path, content: str) -> None:
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _strip_memory_prefix(content: str) -> str:
    cleaned = content.strip()
    prefixes = ("记住：", "记住:", "请记住：", "请记住:", "请记住", "remember:", "correct:", "更正：", "更正:", "纠正：", "纠正:")
    for prefix in prefixes:
        if cleaned.lower().startswith(prefix.lower()):
            return cleaned[len(prefix) :].strip()
    return cleaned


def _extract_field(line: str, field: str) -> str | None:
    match = re.search(rf"{re.escape(field)}:\s*([^|]+)", line)
    return match.group(1).strip() if match else None
