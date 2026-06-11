from __future__ import annotations

from collections import defaultdict
from typing import Any, Awaitable, Callable

Subscriber = Callable[[dict[str, Any]], Awaitable[None] | None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def subscribe(self, event: str, subscriber: Subscriber) -> None:
        self._subscribers[event].append(subscriber)

    async def publish(self, event: str, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {}
        for subscriber in self._subscribers.get(event, []):
            result = subscriber(payload)
            if hasattr(result, "__await__"):
                await result
