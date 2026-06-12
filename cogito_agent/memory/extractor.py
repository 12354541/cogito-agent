from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cogito_agent.agent.state import utc_now_iso
from cogito_agent.memory.markdown_store import MarkdownMemoryStore
from cogito_agent.tracing.redaction import redact_text

if TYPE_CHECKING:
    from cogito_agent.tracing.context import TraceContext
    from cogito_agent.tracing.tracer import Tracer


_SENSITIVE_PATTERNS = re.compile(
    r"(?:"
    r"\bsk-[a-zA-Z0-9]{20,}\b"
    r"|Bearer\s+[a-zA-Z0-9\-._~+/]{20,}"
    r"|api_key['\"]?\s*[:=]\s*['\"][a-zA-Z0-9]{16,}"
    r")",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ExtractedMemory:
    content: str
    category: str = "fact"
    confidence: float = 0.6
    related_memory_ids: list[str] = field(default_factory=list)
    is_correction: bool = False
    is_sensitive: bool = False


@dataclass(slots=True)
class MemoryConflict:
    memory_id_a: str
    memory_id_b: str
    a_content: str
    b_content: str
    conflict_reason: str
    resolution_suggestion: str = ""


class MemoryExtractor:
    def __init__(
        self,
        memory_store: MarkdownMemoryStore,
        max_candidates_per_run: int = 5,
    ) -> None:
        self.memory_store = memory_store
        self.max_candidates = max_candidates_per_run

    def extract_from_conversation(
        self,
        *,
        user_content: str,
        assistant_content: str,
        source_trace_id: str,
        source_ref: str,
        trace: TraceContext | None = None,
        tracer: Tracer | None = None,
    ) -> list[ExtractedMemory]:
        candidates: list[ExtractedMemory] = []
        combined = f"{user_content}\n{assistant_content}"

        if tracer and trace:
            tracer.record_event(
                trace,
                event="memory_extraction_started",
                metadata={"combined_len": len(combined), "source_trace_id": source_trace_id},
            )

        if not self._is_candidate_turn(user_content, assistant_content):
            if tracer and trace:
                tracer.record_event(trace, event="memory_extraction_skipped", metadata={"reason": "not a candidate turn"})
            return candidates

        facts = self._extract_facts(combined)
        for fact in facts:
            gated = self._sensitivity_gate(fact.content)
            if gated.is_sensitive:
                if tracer and trace:
                    tracer.record_event(
                        trace,
                        event="memory_sensitive_filtered",
                        metadata={"original_preview": fact.content[:80], "memory_id": ""},
                    )
                continue
            gated.content = redact_text(gated.content)
            memory_id = self._store_or_update(gated, source_trace_id=source_trace_id, source_ref=source_ref)
            gated.related_memory_ids = list(self._find_related(gated.content, memory_id))
            candidates.append(gated)

            if tracer and trace:
                tracer.record_event(
                    trace,
                    event="memory_extracted",
                    metadata={
                        "memory_id": memory_id,
                        "category": gated.category,
                        "confidence": gated.confidence,
                        "is_correction": gated.is_correction,
                        "related_count": len(gated.related_memory_ids),
                    },
                )

        if tracer and trace:
            tracer.record_event(
                trace,
                event="memory_extraction_finished",
                metadata={"candidate_count": len(candidates)},
            )

        return candidates

    def _is_candidate_turn(self, user_content: str, assistant_content: str) -> bool:
        # Turns with substantive assistant answers are candidates
        text = assistant_content.strip()
        if len(text) < 10:
            return False
        # Skip purely conversational fillers (check as substrings for CJK)
        filler = ("好的", "明白", "收到", "ok", "没问题", "当然", "sure", "got it", "理解了")
        if text.lower() in filler or text.lower().rstrip("。.!！") in filler:
            return False
        return True

    def _extract_facts(self, combined: str) -> list[ExtractedMemory]:
        facts: list[ExtractedMemory] = []

        # Rule: statements about the user (preferences, facts)
        user_fact_patterns = [
            r"(?:我的|用户|user|我爱|我喜欢|我爱吃|我是)(?:的)?(.{5,100})",
            r"(?:我(?:是|叫|在|有|做|会|可以|喜欢|想要|需要|希望|住在|来自))(.{5,100})",
            r"(?:my|i (?:am|work|live|like|love|prefer|need|want|have|use|know|study|play))(.{10,100})",
        ]
        for pattern in user_fact_patterns:
            for match in re.finditer(pattern, combined, re.IGNORECASE):
                content = match.group(1).strip().rstrip(".,!?")
                if len(content) >= 5 and not _looks_temporal(content):
                    facts.append(ExtractedMemory(content=content, category="user_fact", confidence=0.55))

        # Rule: preferences (love/hate/like)
        preference_patterns = [
            r"(?:喜欢|爱|爱吃|欣赏|享受|prefer|love|like|enjoy|favorite)\s+(.{5,80})",
        ]
        for pattern in preference_patterns:
            for match in re.finditer(pattern, combined, re.IGNORECASE):
                content = match.group(1).strip().rstrip(".,!?")
                if len(content) >= 5:
                    facts.append(ExtractedMemory(content=f"likes {content}", category="preference", confidence=0.6))

        # Rule: correction markers
        correction_patterns = [
            r"(?:更正|纠正|correct|not|不对|不是|错了|actually)\s*(?:[:,：]?\s*)(.{8,100})",
        ]
        for pattern in correction_patterns:
            for match in re.finditer(pattern, combined, re.IGNORECASE):
                content = match.group(1).strip().rstrip(".,!?")
                if len(content) >= 8:
                    facts.append(ExtractedMemory(content=content, category="correction", confidence=0.75, is_correction=True))

        # Deduplicate by content hash
        seen: set[str] = set()
        deduped: list[ExtractedMemory] = []
        for f in facts:
            h = hashlib.md5(f.content.encode()).hexdigest()[:8]
            if h not in seen:
                seen.add(h)
                deduped.append(f)

        return deduped[: self.max_candidates]

    def _sensitivity_gate(self, content: str) -> ExtractedMemory:
        if _SENSITIVE_PATTERNS.search(content):
            return ExtractedMemory(content=content, is_sensitive=True)
        # Check for phone numbers, emails, addresses
        if re.search(r"\b\d{11,}\b", content):
            return ExtractedMemory(content=content, is_sensitive=True)
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", content):
            return ExtractedMemory(content=content, is_sensitive=True)
        if re.search(r"(?:password|secret|token|密钥|密码)\s*[:=]\s*\S+", content, re.IGNORECASE):
            return ExtractedMemory(content=content, is_sensitive=True)
        return ExtractedMemory(content=content)

    def _store_or_update(
        self,
        memory: ExtractedMemory,
        *,
        source_trace_id: str,
        source_ref: str,
    ) -> str:
        existing = self.memory_store.list_entries()

        # If correction, forget the old conflicting memory first
        if memory.is_correction:
            for entry in existing:
                if self._likely_contradicts(memory.content, entry.content_preview):
                    if self.memory_store.forget(entry.memory_id):
                        break

        memory_id = self.memory_store.add(
            memory.content,
            source_trace_id=source_trace_id,
            source_ref=source_ref,
            confidence=memory.confidence,
            metadata={
                "category": memory.category,
                "is_correction": memory.is_correction,
                "extracted_at": utc_now_iso(),
            },
        )
        return memory_id

    def _likely_contradicts(self, a: str, b: str) -> bool:
        a_lower = a.lower()
        b_lower = b.lower()

        # Extract meaningful tokens (words + CJK characters)
        a_tokens = {t for t in re.findall(r"[a-z]+|[\u4e00-\u9fff]+", a_lower) if len(t) >= 2}
        b_tokens = {t for t in re.findall(r"[a-z]+|[\u4e00-\u9fff]+", b_lower) if len(t) >= 2}
        common = a_tokens & b_tokens
        if len(common) < 2:
            # fallback: check if one sentence's content words appear as substring in the other
            for tok in list(a_tokens)[:3]:
                if tok in b_lower and len(list(b_tokens & a_tokens)) >= 1:
                    common.add(tok)
        if len(common) < 2:
            return False

        negations = {"不", "没", "no", "not", "don't", "doesn't", "won't", "can't"}
        a_neg = any(n in a_lower for n in negations)
        b_neg = any(n in b_lower for n in negations)
        return a_neg != b_neg

    def _find_related(self, content: str, current_id: str) -> list[str]:
        entries = self.memory_store.list_entries()
        related: list[str] = []
        for entry in entries:
            if entry.memory_id == current_id:
                continue
            a_words = set(content.lower().split())
            b_words = set(entry.content_preview.lower().split())
            overlap = len(a_words & b_words)
            if overlap >= 2:
                related.append(entry.memory_id)
        return related[:3]

    def detect_conflicts(self) -> list[MemoryConflict]:
        entries = self.memory_store.list_entries()
        conflicts: list[MemoryConflict] = []
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if self._likely_contradicts(entries[i].content_preview, entries[j].content_preview):
                    conflicts.append(
                        MemoryConflict(
                            memory_id_a=entries[i].memory_id,
                            memory_id_b=entries[j].memory_id,
                            a_content=entries[i].content_preview,
                            b_content=entries[j].content_preview,
                            conflict_reason="likely contradiction",
                            resolution_suggestion="",
                        )
                    )
        return conflicts


def _looks_temporal(content: str) -> bool:
    # Skip time/date expressions that don't carry memory value
    temp = (
        "现在", "今天", "昨天", "明天", "上午", "下午", "晚上",
        "now", "today", "yesterday", "tomorrow", "morning", "afternoon",
    )
    return any(content.startswith(t) for t in temp)
