from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cogito_agent.proactive.gateway import DataGateway, ProactiveItem
from cogito_agent.proactive.quota import ProactiveQuota
from cogito_agent.proactive.scoring import ProactiveScorer


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
        threshold: float = 0.6,
    ) -> None:
        self.workspace = workspace
        self.gateway = gateway or DataGateway(workspace)
        self.scorer = scorer or ProactiveScorer()
        self.quota = quota or ProactiveQuota(workspace)
        self.threshold = threshold

    def tick_once(self) -> ProactiveDecision:
        items = self.gateway.fetch()
        if not items:
            return ProactiveDecision(False, reason="no_items")
        scored = sorted(((self.scorer.score(item), item) for item in items), key=lambda pair: pair[0], reverse=True)
        score, item = scored[0]
        if score < self.threshold:
            return ProactiveDecision(False, item=item, score=score, reason="below_threshold")
        if not self.quota.can_send():
            return ProactiveDecision(False, item=item, score=score, reason="quota_exceeded", metadata=self.quota.status())
        self.quota.mark_sent()
        return ProactiveDecision(True, item=item, score=score, reason="selected", metadata=self.quota.status())

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "threshold": self.threshold, "quota": self.quota.status()}
