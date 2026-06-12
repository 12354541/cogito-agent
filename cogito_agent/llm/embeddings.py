from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


@dataclass(slots=True)
class OpenAICompatibleEmbeddingClient:
    api_key: str
    base_url: str
    model: str
    timeout: float = 30.0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self.base_url.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "input": texts}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        rows = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        return [list(map(float, row["embedding"])) for row in rows]
