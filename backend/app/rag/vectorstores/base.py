"""Vector store adapter protocol — Qdrant default; Pinecone/Chroma optional."""

from abc import ABC, abstractmethod
from typing import Any


class BaseVectorStore(ABC):
    @abstractmethod
    async def upsert(
        self,
        *,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        ...

    @abstractmethod
    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...
