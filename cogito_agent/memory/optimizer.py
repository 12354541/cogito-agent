from __future__ import annotations

from dataclasses import dataclass

from cogito_agent.memory.consolidation import MemoryConsolidator


@dataclass(slots=True)
class MemoryOptimizerResult:
    promoted_ids: list[str]


class MemoryOptimizer:
    def __init__(self, consolidator: MemoryConsolidator) -> None:
        self.consolidator = consolidator

    def run_once(self, *, source_trace_id: str | None = None) -> MemoryOptimizerResult:
        return MemoryOptimizerResult(promoted_ids=self.consolidator.promote_pending(source_trace_id=source_trace_id))
