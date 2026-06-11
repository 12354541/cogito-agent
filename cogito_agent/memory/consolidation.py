from __future__ import annotations

from pathlib import Path

from cogito_agent.agent.state import utc_now_iso
from cogito_agent.memory.markdown_store import MarkdownMemoryStore


class MemoryConsolidator:
    def __init__(self, workspace: Path, memory_store: MarkdownMemoryStore) -> None:
        self.workspace = workspace
        self.memory_store = memory_store
        self.pending_path = workspace / "memory" / "PENDING.md"
        self.pending_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.pending_path.exists():
            self.pending_path.write_text("# Pending Memory\n\n", encoding="utf-8")

    def maybe_enqueue_user_message(self, content: str, *, trace_id: str) -> bool:
        markers = ("记住", "remember", "请记住")
        lowered = content.lower()
        if not any(marker in lowered for marker in markers):
            return False
        cleaned = content
        for prefix in ("记住：", "记住:", "请记住：", "请记住:", "remember:"):
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()
        with self.pending_path.open("a", encoding="utf-8") as f:
            f.write(f"- created_at: {utc_now_iso()} | source_trace_id: {trace_id} | {cleaned}\n")
        return True

    def promote_pending(self, *, source_trace_id: str | None = None) -> list[str]:
        lines = self.pending_path.read_text(encoding="utf-8").splitlines()
        kept: list[str] = []
        promoted: list[str] = []
        for line in lines:
            if not line.startswith("- "):
                kept.append(line)
                continue
            content = line.split("|")[-1].strip()
            if not content:
                continue
            promoted.append(self.memory_store.add(content, source_trace_id=source_trace_id))
        self.pending_path.write_text("\n".join(kept).strip() + "\n\n", encoding="utf-8")
        return promoted
