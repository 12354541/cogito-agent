from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cogito_agent.memory.markdown_store import MarkdownMemoryStore
from cogito_agent.memory.models import MemoryHit, RagHit
from cogito_agent.memory.vector_store import InMemoryVectorStore
from cogito_agent.tracing.context import TraceContext

if TYPE_CHECKING:
    from cogito_agent.tracing.tracer import Tracer


@dataclass(slots=True)
class RetrievalResult:
    memory_hits: list[MemoryHit] = field(default_factory=list)
    doc_hits: list[RagHit] = field(default_factory=list)

    def all_prompt_hits(self) -> list[MemoryHit | RagHit]:
        return [*self.memory_hits, *self.doc_hits]


class MemoryRetriever:
    def __init__(
        self,
        store: MarkdownMemoryStore,
        *,
        vector_store: InMemoryVectorStore | None = None,
        top_k: int = 5,
    ) -> None:
        self.store = store
        self.vector_store = vector_store
        self.top_k = top_k

    def search(
        self,
        query: str,
        *,
        trace: TraceContext | None = None,
        tracer: "Tracer | None" = None,
    ) -> RetrievalResult:
        if trace and tracer:
            tracer.record_event(
                trace,
                event="memory_retrieval_started",
                metadata={"query_preview": query[:120], "top_k": self.top_k},
            )
        memory_hits = self.store.search(query, top_k=self.top_k)
        doc_hits = [
            RagHit(
                doc_id=hit.doc_id,
                source=hit.source,
                content_preview=hit.content_preview,
                score=hit.score,
                metadata=hit.metadata,
            )
            for hit in (self.vector_store.search(query, top_k=self.top_k) if self.vector_store else [])
        ]
        if trace and tracer:
            tracer.record_event(
                trace,
                event="memory_retrieval_finished",
                metadata={
                    "memory_hit_count": len(memory_hits),
                    "doc_hit_count": len(doc_hits),
                    "memory_hits": [{"memory_id": hit.memory_id, "score": hit.score} for hit in memory_hits],
                    "doc_hits": [{"doc_id": hit.doc_id, "score": hit.score, "source": hit.source} for hit in doc_hits],
                },
            )
        return RetrievalResult(memory_hits=memory_hits, doc_hits=doc_hits)
