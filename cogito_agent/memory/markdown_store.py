from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
        self.journal_dir = self.memory_dir / "journal"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.memory_dir / "memory_audit.jsonl"
        if not self.path.exists():
            self.path.write_text("# Cogito Memory\n\n", encoding="utf-8")

    def add(
        self,
        content: str,
        *,
        source_trace_id: str | None = None,
        source_ref: str | None = None,
        confidence: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        memory_id = new_id("mem")
        safe_content = " ".join(content.strip().split())
        created_at = utc_now_iso()
        correction = _looks_like_correction(safe_content)
        line = (
            f"- id: {memory_id} | created_at: {created_at} | source_trace_id: {source_trace_id or ''} | "
            f"source_ref: {source_ref or ''} | confidence: {confidence:.2f} | type: {'correction' if correction else 'fact'} | {safe_content}\n"
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
        self._journal(
            {
                "event": "memory_added",
                "memory_id": memory_id,
                "created_at": created_at,
                "source_trace_id": source_trace_id,
                "source_ref": source_ref,
                "confidence": confidence,
                "type": "correction" if correction else "fact",
                "content": safe_content,
                "metadata": metadata or {},
            }
        )
        return memory_id

    def list_entries(self) -> list[MemoryHit]:
        entries: list[MemoryHit] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- id: "):
                continue
            parts = [part.strip() for part in line.removeprefix("- ").split("|")]
            fields: dict[str, str] = {}
            content = parts[-1] if parts else ""
            for part in parts[:-1]:
                if ":" not in part:
                    continue
                key, value = part.split(":", 1)
                fields[key.strip()] = value.strip()
            memory_id = fields.get("id")
            if not memory_id:
                continue
            entries.append(
                MemoryHit(
                    memory_id=memory_id,
                    source=str(self.path),
                    content_preview=content[:500],
                    score=float(fields.get("confidence") or 1.0),
                    metadata=fields,
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
        self._journal({"event": "memory_deleted", "memory_id": memory_id, "created_at": utc_now_iso()})
        return True

    def _journal(self, payload: dict[str, Any]) -> None:
        today = utc_now_iso()[:10]
        journal_path = self.journal_dir / f"{today}.jsonl"
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with journal_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _looks_like_correction(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in ("correct", "correction", "更正", "纠正", "不是"))
