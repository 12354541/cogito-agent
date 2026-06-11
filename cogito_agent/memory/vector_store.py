from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class VectorDocument:
    doc_id: str
    source: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VectorHit:
    doc_id: str
    source: str
    content_preview: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class InMemoryVectorStore:
    """Dependency-free lexical vector store.

    This is intentionally simple: it gives the project a stable RAG contract
    before an embedding backend is introduced.
    """

    def __init__(self) -> None:
        self._documents: dict[str, VectorDocument] = {}

    def upsert(self, document: VectorDocument) -> None:
        self._documents[document.doc_id] = document

    def add_text(self, *, doc_id: str, source: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self.upsert(VectorDocument(doc_id=doc_id, source=source, content=content, metadata=metadata or {}))

    def search(self, query: str, *, top_k: int = 5) -> list[VectorHit]:
        query_vec = _term_vector(query)
        hits: list[VectorHit] = []
        for document in self._documents.values():
            score = _cosine(query_vec, _term_vector(document.content))
            if score <= 0:
                continue
            hits.append(
                VectorHit(
                    doc_id=document.doc_id,
                    source=document.source,
                    content_preview=document.content[:500],
                    score=score,
                    metadata=document.metadata,
                )
            )
        return sorted(hits, key=lambda item: item.score, reverse=True)[:top_k]

    @classmethod
    def from_workspace_docs(cls, workspace: Path, *, chunk_chars: int = 1200) -> "InMemoryVectorStore":
        store = cls()
        docs_dir = workspace / "docs"
        if not docs_dir.exists():
            return store
        for path in docs_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for index, chunk in enumerate(_chunks(text, chunk_chars)):
                store.add_text(
                    doc_id=f"{path.relative_to(workspace)}#{index}",
                    source=str(path),
                    content=chunk,
                    metadata={"path": str(path), "chunk": index},
                )
        return store


def _chunks(text: str, chunk_chars: int) -> list[str]:
    return [text[index : index + chunk_chars] for index in range(0, len(text), chunk_chars) if text[index : index + chunk_chars].strip()]


def _term_vector(text: str) -> dict[str, float]:
    terms = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    vector: dict[str, float] = {}
    for term in terms:
        vector[term] = vector.get(term, 0.0) + 1.0
    return vector


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm)
