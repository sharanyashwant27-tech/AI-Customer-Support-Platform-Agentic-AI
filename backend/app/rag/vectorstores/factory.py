"""Vector store factory — Qdrant, Pinecone, Chroma (+ in-memory fallback)."""

from __future__ import annotations

import math
import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.observability.metrics import RAG_RETRIEVALS_TOTAL
from app.rag.vectorstores.base import BaseVectorStore

logger = get_logger(__name__)

VECTOR_STORE_CATALOG: dict[str, dict[str, Any]] = {
    "qdrant": {
        "label": "Qdrant",
        "description": "Default local/self-hosted vector database",
    },
    "pinecone": {
        "label": "Pinecone",
        "description": "Managed cloud vector database",
    },
    "chroma": {
        "label": "Chroma",
        "description": "Embedded / persistent local vector database",
    },
}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class InMemoryVectorStore(BaseVectorStore):
    """Process-local store used when Qdrant/Pinecone/Chroma are unavailable."""

    def __init__(self, collection: str = "knowledge_base") -> None:
        self.collection = collection
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []
        self._payloads: list[dict[str, Any]] = []

    async def upsert(
        self,
        *,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        for i, vec, payload in zip(ids, vectors, payloads, strict=True):
            if i in self._ids:
                idx = self._ids.index(i)
                self._vectors[idx] = vec
                self._payloads[idx] = payload
            else:
                self._ids.append(i)
                self._vectors.append(vec)
                self._payloads.append(payload)

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[float, int]] = []
        for idx, stored in enumerate(self._vectors):
            payload = self._payloads[idx]
            if filters:
                if any(payload.get(k) != v for k, v in filters.items()):
                    continue
            scored.append((_cosine(vector, stored), idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, idx in scored[:top_k]:
            results.append(
                {
                    "id": self._ids[idx],
                    "score": score,
                    "payload": self._payloads[idx],
                }
            )
        RAG_RETRIEVALS_TOTAL.labels(store="memory", status="success").inc()
        return results


class QdrantVectorStore(BaseVectorStore):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        collection: str,
        dimension: int,
    ) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels

        self.collection = collection
        self.dimension = dimension
        self._models = qmodels
        self.client = QdrantClient(
            host=host, port=port, timeout=5.0, check_compatibility=False
        )
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        names = {c.name for c in self.client.get_collections().collections}
        if self.collection not in names:
            from qdrant_client.http import models as qmodels

            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qmodels.VectorParams(
                    size=self.dimension,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created", collection=self.collection)

    async def upsert(
        self,
        *,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        safe_points = []
        for i, vector, payload in zip(ids, vectors, payloads, strict=True):
            point_id = i if _is_uuid(i) else str(uuid.uuid5(uuid.NAMESPACE_URL, i))
            safe_points.append(
                self._models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={**payload, "doc_id": i},
                )
            )
        self.client.upsert(collection_name=self.collection, points=safe_points)

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        qfilter = None
        if filters:
            qfilter = self._models.Filter(
                must=[
                    self._models.FieldCondition(
                        key=k,
                        match=self._models.MatchValue(value=v),
                    )
                    for k, v in filters.items()
                ]
            )
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=top_k,
            query_filter=qfilter,
        )
        hits = getattr(response, "points", response) or []
        RAG_RETRIEVALS_TOTAL.labels(store="qdrant", status="success").inc()
        results: list[dict[str, Any]] = []
        for hit in hits:
            results.append(
                {
                    "id": str(hit.id),
                    "score": float(getattr(hit, "score", 0.0) or 0.0),
                    "payload": hit.payload or {},
                }
            )
        return results


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except Exception:
        return False


_STORE: BaseVectorStore | None = None


def list_vector_stores() -> list[dict[str, Any]]:
    settings = get_settings()
    return [
        {
            "id": key,
            **meta,
            "active": settings.vector_store == key,
        }
        for key, meta in VECTOR_STORE_CATALOG.items()
    ]


def get_vector_store(force_memory: bool = False) -> BaseVectorStore:
    """
    Resolve vector database.

    Store inside: Qdrant | Pinecone | Chroma
    (falls back to in-memory when the chosen backend is unavailable)
    """
    global _STORE
    if force_memory:
        if _STORE is None or not isinstance(_STORE, InMemoryVectorStore):
            _STORE = InMemoryVectorStore()
        return _STORE
    if _STORE is not None:
        return _STORE

    settings = get_settings()
    chosen = (settings.vector_store or "qdrant").lower()

    if chosen == "qdrant":
        try:
            _STORE = QdrantVectorStore(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                collection=settings.qdrant_collection,
                dimension=get_embedding_dimension_hint(),
            )
            logger.info("vector_store_qdrant", host=settings.qdrant_host, port=settings.qdrant_port)
            return _STORE
        except Exception as exc:
            logger.warning("qdrant_unavailable_fallback_memory", error=str(exc))
    elif chosen == "pinecone":
        try:
            from app.rag.vectorstores.pinecone_store import PineconeVectorStore

            if not settings.pinecone_api_key:
                raise RuntimeError("PINECONE_API_KEY is empty")
            _STORE = PineconeVectorStore(
                api_key=settings.pinecone_api_key,
                index_name=settings.pinecone_index,
                dimension=get_embedding_dimension_hint(),
                environment=settings.pinecone_environment,
            )
            logger.info("vector_store_pinecone", index=settings.pinecone_index)
            return _STORE
        except Exception as exc:
            logger.warning("pinecone_unavailable_fallback_memory", error=str(exc))
    elif chosen == "chroma":
        try:
            from app.rag.vectorstores.chroma_store import ChromaVectorStore

            _STORE = ChromaVectorStore(
                persist_dir=settings.chroma_persist_dir,
                collection=settings.qdrant_collection,
                dimension=get_embedding_dimension_hint(),
            )
            logger.info("vector_store_chroma", path=settings.chroma_persist_dir)
            return _STORE
        except Exception as exc:
            logger.warning("chroma_unavailable_fallback_memory", error=str(exc))

    _STORE = InMemoryVectorStore(collection=settings.qdrant_collection)
    logger.info("vector_store_memory")
    return _STORE


def get_embedding_dimension_hint() -> int:
    from app.rag.embeddings.factory import get_embedding_adapter

    adapter = get_embedding_adapter()
    return int(getattr(adapter, "dimension", 384) or 384)


def reset_vector_store() -> None:
    global _STORE
    _STORE = None
