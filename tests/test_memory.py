from __future__ import annotations

from cogito_agent.memory.consolidation import MemoryConsolidator
from cogito_agent.memory.extractor import ExtractedMemory, MemoryExtractor, _looks_temporal
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


def test_extractor_skips_short_assistant(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    extractor = MemoryExtractor(store)
    candidates = extractor.extract_from_conversation(
        user_content="hi", assistant_content="ok", source_trace_id="t1", source_ref="r1"
    )
    assert candidates == []


def test_extractor_extracts_user_fact(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    extractor = MemoryExtractor(store)
    candidates = extractor.extract_from_conversation(
        user_content="我是工程师，喜欢用 Python 开发。",
        assistant_content="好的，我知道了。你是一名工程师。",
        source_trace_id="t2",
        source_ref="r2",
    )
    assert len(candidates) >= 1
    entry = store.list_entries()
    assert len(entry) >= 1
    assert "工程师" in entry[0].content_preview


def test_extractor_correction_forgets_old(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    old_id = store.add("likes coffee", source_trace_id="t_old", source_ref="r_old", confidence=0.6)

    extractor = MemoryExtractor(store)
    mem = extractor._store_or_update(
        ExtractedMemory(content="does not like coffee", category="correction", confidence=0.75, is_correction=True),
        source_trace_id="t3",
        source_ref="r3",
    )

    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0].memory_id != old_id
    assert "does not like coffee" in entries[0].content_preview


def test_extractor_filters_sensitive_data(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    extractor = MemoryExtractor(store)
    candidates = extractor.extract_from_conversation(
        user_content="我的密码是 supersecret123",
        assistant_content="已记录。",
        source_trace_id="t4",
        source_ref="r4",
    )
    assert all(not c.is_sensitive for c in candidates)
    entries = store.list_entries()
    assert len(entries) == 0


def test_extractor_detects_conflicts(tmp_path):
    store = MarkdownMemoryStore(tmp_path)
    store.add("user likes Python", source_trace_id="t_a", source_ref="r_a", confidence=0.6)
    store.add("user does not like Python", source_trace_id="t_b", source_ref="r_b", confidence=0.6)
    extractor = MemoryExtractor(store)
    conflicts = extractor.detect_conflicts()
    assert len(conflicts) >= 1


def test_looks_temporal():
    assert _looks_temporal("现在几点了") is True
    assert _looks_temporal("今天天气不错") is True
    assert _looks_temporal("我喜欢编程") is False
