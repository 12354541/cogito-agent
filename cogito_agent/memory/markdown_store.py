from __future__ import annotations

import re
from pathlib import Path

from cogito_agent.agent.state import new_id, utc_now_iso
from cogito_agent.memory.models import MemoryHit


class MarkdownMemoryStore:
    """Small Markdown-backed memory store.

    Facts are stored as one bullet per line so the first implementation stays
    inspectable and easy to edit by hand.
    """

    def __init__(self, workspace: Path) -> None:
        self.memory_dir = workspace / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.memory_dir / "MEMORY.md"
        if not self.path.exists():
            self.path.write_text("# Cogito Memory\n\n", encoding="utf-8")

    def add(self, content: str, *, source_trace_id: str | None = None) -> str:
        memory_id = new_id("mem")
        safe_content = " ".join(content.strip().split())
        line = f"- id: {memory_id} | created_at: {utc_now_iso()} | source_trace_id: {source_trace_id or ''} | {safe_content}\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
        return memory_id

    def list_entries(self) -> list[MemoryHit]:
        entries: list[MemoryHit] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- id: "):
                continue
            match = re.match(r"- id: (?P<id>[^|]+)\|(?P<meta>.*)\|(?P<content>.*)", line)
            if not match:
                continue
            entries.append(
                MemoryHit(
                    memory_id=match.group("id").strip(),
                    source=str(self.path),
                    content_preview=match.group("content").strip()[:500],
                    score=1.0,
                )
            )
        return entries

    def search(self, query: str, *, top_k: int = 5) -> list[MemoryHit]:
        query_terms = {term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query)}
        hits: list[MemoryHit] = []
        for entry in self.list_entries():
            content_terms = {term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", entry.content_preview)}
            overlap = len(query_terms & content_terms)
            if overlap > 0 or any(term in entry.content_preview.lower() for term in query_terms):
                entry.score = overlap / max(len(query_terms), 1)
                hits.append(entry)
        return sorted(hits, key=lambda item: item.score, reverse=True)[:top_k]

    def forget(self, memory_id: str) -> bool:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if not line.startswith(f"- id: {memory_id} ")]
        if len(kept) == len(lines):
            return False
        self.path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return True
