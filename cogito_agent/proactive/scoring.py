from __future__ import annotations

from cogito_agent.proactive.gateway import ProactiveItem


class ProactiveScorer:
    def score(self, item: ProactiveItem) -> float:
        if item.channel == "alert":
            return 1.0
        keywords = ("urgent", "重要", "deadline", "due", "提醒")
        keyword_score = 0.25 if any(keyword.lower() in (item.title + item.body).lower() for keyword in keywords) else 0.0
        return min(1.0, 0.2 + item.priority * 0.1 + keyword_score)
