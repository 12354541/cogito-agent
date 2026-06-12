from __future__ import annotations

from cogito_agent.memory.consolidation import MemoryConsolidator
from cogito_agent.memory.markdown_store import MarkdownMemoryStore
from cogito_agent.memory.retriever import MemoryRetriever
from cogito_agent.memory.vector_store import InMemoryVectorStore


class FakeEmbeddingClient:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append([1.0, 0.0] if "python" in lowered else [0.0, 1.0])
        return vectors


class FakeReranker:
    def rerank(self, query: str, documents: list[str], *, top_k: int) -> list[tuple[int, float]]:
        scored = [(index, 10.0 if "second" in document else 1.0) for index, document in enumerate(documents)]
        return sorted(scored, key=lambda item: item[1], reverse=True)[:top_k]


def test_markdown_memory_store_add_search_forget(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    memory_id = store.add("用户喜欢用 Python 写 AI Agent 项目。", source_trace_id="trace_test", source_ref="trace_test", confidence=0.8)

    hits = store.search("Python Agent")

    assert hits
    assert hits[0].memory_id == memory_id
    assert "Python" in hits[0].content_preview
    assert hits[0].metadata["source_trace_id"] == "trace_test"
    assert hits[0].metadata["confidence"] == "0.80"
    assert (tmp_path / "memory" / "memory_audit.jsonl").exists()
    assert store.forget(memory_id) is True
    assert store.search("Python Agent") == []


def test_memory_consolidator_tracks_history_and_recent_context(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    consolidator = MemoryConsolidator(tmp_path, store)

    queued = consolidator.maybe_enqueue_user_message("记住：我喜欢 Python", trace_id="trace_memory")
    promoted = consolidator.promote_pending()

    assert queued is True
    assert promoted
    assert "trace_memory" in (tmp_path / "memory" / "HISTORY.md").read_text(encoding="utf-8")
    assert "我喜欢 Python" in (tmp_path / "memory" / "RECENT_CONTEXT.md").read_text(encoding="utf-8")


def test_retriever_returns_doc_hits(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("Cogito supports drift background task execution.", encoding="utf-8")
    memory_store = MarkdownMemoryStore(tmp_path)
    vector_store = InMemoryVectorStore.from_workspace_docs(tmp_path)
    retriever = MemoryRetriever(memory_store, vector_store=vector_store, top_k=3)

    result = retriever.search("drift background")

    assert result.doc_hits
    assert "guide.md" in result.doc_hits[0].source


def test_vector_store_uses_embedding_client(tmp_path):
    store = InMemoryVectorStore(embedding_client=FakeEmbeddingClient())
    store.add_text(doc_id="python", source="python.md", content="Python agent runtime")
    store.add_text(doc_id="weather", source="weather.md", content="Weather forecast")

    hits = store.search("Python language", top_k=2)

    assert hits[0].doc_id == "python"
    assert hits[0].score > 0


def test_vector_store_persists_index(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("Cogito supports persistent vector indexes.", encoding="utf-8")

    first = InMemoryVectorStore.from_workspace_docs(tmp_path)
    second = InMemoryVectorStore.from_workspace_docs(tmp_path)

    assert (tmp_path / "vector_index.json").exists()
    assert first.search("persistent vector")
    assert second.search("persistent vector")


def test_retriever_uses_reranker_for_doc_hits(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "first.md").write_text("drift first document", encoding="utf-8")
    (docs / "second.md").write_text("drift second document", encoding="utf-8")
    memory_store = MarkdownMemoryStore(tmp_path)
    vector_store = InMemoryVectorStore.from_workspace_docs(tmp_path)
    retriever = MemoryRetriever(memory_store, vector_store=vector_store, reranker=FakeReranker(), top_k=2)

    result = retriever.search("drift document")

    assert result.doc_hits[0].metadata["reranked"] is True
    assert "second.md" in result.doc_hits[0].source
