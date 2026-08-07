"""Optional Pinecone vector store adapter."""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.observability.metrics import RAG_RETRIEVALS_TOTAL
from app.rag.vectorstores.base import BaseVectorStore

logger = get_logger(__name__)


class PineconeVectorStore(BaseVectorStore):
    def __init__(
        self,
        *,
        api_key: str,
        index_name: str,
        dimension: int,
        environment: str = "us-east-1",
    ) -> None:
        from pinecone import Pinecone

        self.dimension = dimension
        self.index_name = index_name
        self.environment = environment
        self._pc = Pinecone(api_key=api_key)
        existing = {i["name"] for i in self._pc.list_indexes()}
        if index_name not in existing:
            from pinecone import ServerlessSpec

            self._pc.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region=environment),
            )
            logger.info("pinecone_index_created", index=index_name, region=environment)
        self.index = self._pc.Index(index_name)

    async def upsert(
        self,
        *,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        self.index.upsert(
            vectors=[
                {"id": i, "values": v, "metadata": _flatten(p)}
                for i, v, p in zip(ids, vectors, payloads, strict=True)
            ]
        )

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        response = self.index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=True,
            filter=filters or None,
        )
        RAG_RETRIEVALS_TOTAL.labels(store="pinecone", status="success").inc()
        matches = getattr(response, "matches", None) or response.get("matches", [])
        results = []
        for match in matches:
            mid = getattr(match, "id", None) or match.get("id")
            score = getattr(match, "score", None) or match.get("score", 0.0)
            meta = getattr(match, "metadata", None) or match.get("metadata") or {}
            results.append({"id": str(mid), "score": float(score or 0.0), "payload": meta})
        return results


def _flatten(payload: dict[str, Any]) -> dict[str, Any]:
    """Pinecone metadata must be flat primitives."""
    flat: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            flat[key] = value if value is not None else ""
        else:
            flat[key] = str(value)[:1000]
    return flat
