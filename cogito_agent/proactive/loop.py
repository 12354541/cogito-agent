from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cogito_agent.proactive.agent_tick import AgentTick, MessagePushStore
from cogito_agent.proactive.gateway import DataGateway, ProactiveItem
from cogito_agent.proactive.quota import ProactiveQuota
from cogito_agent.proactive.scoring import ProactiveScorer
from cogito_agent.tools.schedule import ScheduleStore
from cogito_agent.tracing.tracer import Tracer


@dataclass(slots=True)
class ProactiveDecision:
    should_send: bool
    item: ProactiveItem | None = None
    score: float = 0.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ProactiveLoop:
    def __init__(
        self,
        workspace: Path,
        *,
        gateway: DataGateway | None = None,
        scorer: ProactiveScorer | None = None,
        quota: ProactiveQuota | None = None,
        push_store: MessagePushStore | None = None,
        schedule_store: ScheduleStore | None = None,
        tracer: Tracer | None = None,
        threshold: float = 0.6,
        enabled: bool = True,
    ) -> None:
        self.workspace = workspace
        self.gateway = gateway or DataGateway(workspace)
        self.scorer = scorer or ProactiveScorer()
        self.quota = quota or ProactiveQuota(workspace)
        self.push_store = push_store or MessagePushStore(workspace)
        self.schedule_store = schedule_store
        self.tracer = tracer
        self.threshold = threshold
        self.enabled = enabled
        self.agent_tick = AgentTick(self.scorer, threshold)

    def tick_once(self) -> ProactiveDecision:
        if not self.enabled:
            return ProactiveDecision(False, reason="disabled")
        trace = (
            self.tracer.start_trace(session_id="proactive", user_message_preview="proactive_tick", metadata={"channel": "proactive"})
            if self.tracer
            else None
        )
        items = [*self.gateway.fetch(), *self._due_schedule_items()]
        if trace and self.tracer:
            self.tracer.record_event(trace, event="proactive_items_fetched", metadata={"count": len(items)})
        if not items:
            return self._finish(trace, ProactiveDecision(False, reason="no_items"))
        item, score, reason = self.agent_tick.choose(items)
        if item is None:
            return self._finish(trace, ProactiveDecision(False, reason=reason))
        if reason != "selected":
            return self._finish(trace, ProactiveDecision(False, item=item, score=score, reason=reason))
        block_reason = self.quota.block_reason()
        if block_reason:
            return self._finish(trace, ProactiveDecision(False, item=item, score=score, reason=block_reason, metadata=self.quota.status()))
        self.quota.mark_sent()
        message = self.push_store.push(item, score=score, reason=reason)
        if self.schedule_store and item.metadata.get("schedule_id"):
            self.schedule_store.mark_triggered(str(item.metadata["schedule_id"]))
        decision = ProactiveDecision(
            True,
            item=item,
            score=score,
            reason=reason,
            metadata={**self.quota.status(), "message_id": message.message_id},
        )
        return self._finish(trace, decision)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "threshold": self.threshold,
            "quota": self.quota.status(),
            "outbox_count": len(self.push_store.list()),
        }

    def _due_schedule_items(self) -> list[ProactiveItem]:
        if not self.schedule_store:
            return []
        return [
            ProactiveItem(
                item_id=f"schedule:{item.schedule_id}",
                channel="alert",
                title=item.name,
                body=item.prompt,
                priority=5,
                metadata={"schedule_id": item.schedule_id, "source": "schedule"},
            )
            for item in self.schedule_store.due()
        ]

    def _finish(self, trace: Any, decision: ProactiveDecision) -> ProactiveDecision:
        if trace and self.tracer:
            self.tracer.record_event(
                trace,
                event="proactive_decision",
                metadata={
                    "should_send": decision.should_send,
                    "reason": decision.reason,
                    "score": decision.score,
                    "item_id": decision.item.item_id if decision.item else None,
                },
            )
            self.tracer.finish_trace(trace, status="ok", final_response_preview=decision.reason)
            decision.metadata = {**decision.metadata, "trace_id": trace.trace_id}
        return decision
