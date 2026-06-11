from __future__ import annotations

from cogito_agent.memory.markdown_store import MarkdownMemoryStore
from cogito_agent.memory.retriever import MemoryRetriever
from cogito_agent.memory.vector_store import InMemoryVectorStore


def test_markdown_memory_store_add_search_forget(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    memory_id = store.add("用户喜欢用 Python 写 AI Agent 项目。", source_trace_id="trace_test")

    hits = store.search("Python Agent")

    assert hits
    assert hits[0].memory_id == memory_id
    assert "Python" in hits[0].content_preview
    assert store.forget(memory_id) is True
    assert store.search("Python Agent") == []


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
