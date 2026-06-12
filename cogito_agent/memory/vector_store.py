from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cogito_agent.llm.embeddings import EmbeddingClient


@dataclass(slots=True)
class VectorDocument:
    doc_id: str
    source: str
    content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VectorHit:
    doc_id: str
    source: str
    content_preview: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class InMemoryVectorStore:
    """In-memory document store with optional embedding-backed search.

    Without an embedding client it falls back to dependency-free lexical
    cosine search, keeping local tests and no-key setups deterministic.
    """

    def __init__(self, embedding_client: EmbeddingClient | None = None, index_path: Path | None = None) -> None:
        self.embedding_client = embedding_client
        self.index_path = index_path
        self._documents: dict[str, VectorDocument] = {}
        if self.index_path and self.index_path.exists():
            self._load_index()

    def upsert(self, document: VectorDocument) -> None:
        self._documents[document.doc_id] = document
        self._save_index()

    def add_text(self, *, doc_id: str, source: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        content_hash = _hash_text(content)
        existing = self._documents.get(doc_id)
        if existing and existing.metadata.get("content_hash") == content_hash:
            return
        embedding = None
        if self.embedding_client:
            embedding = self.embedding_client.embed_texts([content])[0]
        merged_metadata = {**(metadata or {}), "content_hash": content_hash}
        self.upsert(VectorDocument(doc_id=doc_id, source=source, content=content, embedding=embedding, metadata=merged_metadata))

    def search(self, query: str, *, top_k: int = 5) -> list[VectorHit]:
        if self.embedding_client:
            return self._semantic_search(query, top_k=top_k)
        return self._lexical_search(query, top_k=top_k)

    def _semantic_search(self, query: str, *, top_k: int) -> list[VectorHit]:
        query_embedding = self.embedding_client.embed_texts([query])[0]
        hits: list[VectorHit] = []
        for document in self._documents.values():
            if document.embedding is None:
                continue
            score = _cosine_dense(query_embedding, document.embedding)
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

    def _lexical_search(self, query: str, *, top_k: int) -> list[VectorHit]:
        query_vec = _term_vector(query)
        hits: list[VectorHit] = []
        for document in self._documents.values():
            score = _cosine_sparse(query_vec, _term_vector(document.content))
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
    def from_workspace_docs(
        cls,
        workspace: Path,
        *,
        chunk_chars: int = 1200,
        embedding_client: EmbeddingClient | None = None,
        persist: bool = True,
    ) -> "InMemoryVectorStore":
        index_path = workspace / "vector_index.json" if persist else None
        store = cls(embedding_client=embedding_client, index_path=index_path)
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

    def _load_index(self) -> None:
        if not self.index_path:
            return
        data = json.loads(self.index_path.read_text(encoding="utf-8") or "[]")
        for item in data:
            self._documents[item["doc_id"]] = VectorDocument(**item)

    def _save_index(self) -> None:
        if not self.index_path:
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(document) for document in self._documents.values()]
        self.index_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _chunks(text: str, chunk_chars: int) -> list[str]:
    return [text[index : index + chunk_chars] for index in range(0, len(text), chunk_chars) if text[index : index + chunk_chars].strip()]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _term_vector(text: str) -> dict[str, float]:
    terms = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    vector: dict[str, float] = {}
    for term in terms:
        vector[term] = vector.get(term, 0.0) + 1.0
    return vector


def _cosine_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm)


def _cosine_dense(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm)
