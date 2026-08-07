"""Optional Chroma vector store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.observability.metrics import RAG_RETRIEVALS_TOTAL
from app.rag.vectorstores.base import BaseVectorStore

logger = get_logger(__name__)


class ChromaVectorStore(BaseVectorStore):
    def __init__(self, *, persist_dir: str, collection: str, dimension: int) -> None:
        import chromadb

        self.dimension = dimension
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("chroma_collection_ready", collection=collection, path=persist_dir)

    async def upsert(
        self,
        *,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        documents = [str(p.get("text") or "") for p in payloads]
        metadatas = [_safe_meta(p) for p in payloads]
        self._collection.upsert(
            ids=ids,
            embeddings=vectors,
            documents=documents,
            metadatas=metadatas,
        )

    async def search(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        where = filters or None
        response = self._collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )
        RAG_RETRIEVALS_TOTAL.labels(store="chroma", status="success").inc()
        ids = (response.get("ids") or [[]])[0]
        metas = (response.get("metadatas") or [[]])[0]
        docs = (response.get("documents") or [[]])[0]
        dists = (response.get("distances") or [[]])[0]
        results = []
        for i, meta, doc, dist in zip(ids, metas, docs, dists, strict=False):
            payload = dict(meta or {})
            if doc and "text" not in payload:
                payload["text"] = doc
            # Chroma returns distance; convert to similarity-ish score
            score = 1.0 - float(dist or 0.0)
            results.append({"id": str(i), "score": score, "payload": payload})
        return results


def _safe_meta(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "text":
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif value is None:
            continue
        else:
            out[key] = str(value)[:500]
    return out
