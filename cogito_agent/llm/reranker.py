from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


class RerankerClient(Protocol):
    def rerank(self, query: str, documents: list[str], *, top_k: int) -> list[tuple[int, float]]:
        raise NotImplementedError


@dataclass(slots=True)
class OpenAICompatibleRerankerClient:
    api_key: str
    base_url: str
    model: str
    timeout: float = 30.0

    def rerank(self, query: str, documents: list[str], *, top_k: int) -> list[tuple[int, float]]:
        if not documents:
            return []
        url = f"{self.base_url.rstrip('/')}/rerank"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_k,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        results: list[tuple[int, float]] = []
        for item in data.get("results", []):
            index = int(item.get("index", 0))
            score = float(item.get("relevance_score", item.get("score", 0.0)))
            results.append((index, score))
        return results
