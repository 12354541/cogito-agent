from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cogito_agent.agent.state import new_id, utc_now_iso
from cogito_agent.proactive.gateway import ProactiveItem
from cogito_agent.proactive.scoring import ProactiveScorer


@dataclass(slots=True)
class PushedMessage:
    message_id: str
    channel: str
    title: str
    body: str
    item_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


class MessagePushStore:
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "proactive_outbox.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def push(self, item: ProactiveItem, *, score: float, reason: str) -> PushedMessage:
        message = PushedMessage(
            message_id=new_id("push"),
            channel=item.channel,
            title=item.title,
            body=item.body,
            item_id=item.item_id,
            metadata={"score": score, "reason": reason, **item.metadata},
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(message), ensure_ascii=False, default=str) + "\n")
        return message

    def list(self) -> list[PushedMessage]:
        if not self.path.exists():
            return []
        messages: list[PushedMessage] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                messages.append(PushedMessage(**json.loads(line)))
        return messages


class AgentTick:
    def __init__(self, scorer: ProactiveScorer, threshold: float) -> None:
        self.scorer = scorer
        self.threshold = threshold

    def choose(self, items: list[ProactiveItem]) -> tuple[ProactiveItem | None, float, str]:
        if not items:
            return None, 0.0, "no_items"
        scored = sorted(((self.scorer.score(item), item) for item in items), key=lambda pair: pair[0], reverse=True)
        score, item = scored[0]
        if score < self.threshold:
            return item, score, "below_threshold"
        return item, score, "selected"
