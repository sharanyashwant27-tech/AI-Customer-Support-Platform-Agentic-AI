"""RAG Pipeline

Knowledge Sources
  PDFs · Product Manuals · FAQs · Policies · Knowledge Base
  Emails · Release Notes · Internal Documentation

Pipeline
  Documents → Chunking → Cleaning → Embeddings → Vector DB
  → Retriever → LLM → Answer
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import LLMMessage, StubLLMAdapter, get_llm_adapter
from app.observability.metrics import RAG_RETRIEVALS_TOTAL
from app.rag.chunking.splitter import chunk_text
from app.rag.cleaning import clean_chunks, clean_document_text
from app.rag.embeddings.factory import get_embedding_adapter
from app.rag.ingestion.loaders import LoadedDocument, load_bytes, load_markdown
from app.rag.sources import KNOWLEDGE_SOURCES, infer_knowledge_source
from app.rag.vectorstores.factory import get_vector_store

logger = get_logger(__name__)

PIPELINE_STAGES = [
    "documents",
    "chunking",
    "cleaning",
    "embeddings",
    "vector_db",
    "retriever",
    "llm",
    "answer",
]


class RAGPipeline:
    """
    Full RAG path:

    Documents → Chunking → Cleaning → Embeddings → Vector DB
    → Retriever → LLM → Answer
    """

    # ------------------------------------------------------------------
    # Ingest: Documents → Chunking → Cleaning → Embeddings → Vector DB
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        document: LoadedDocument,
        *,
        collection: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
        knowledge_source: str | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        document_id = str(uuid.uuid4())
        source_type = infer_knowledge_source(
            filename=document.source,
            file_type=document.file_type,
            explicit=knowledge_source
            or (extra_metadata or {}).get("knowledge_source")
            or document.metadata.get("knowledge_source"),
        )

        # Documents (normalized)
        content = clean_document_text(document.content)
        meta = {
            "document_id": document_id,
            "title": document.title,
            "source": document.source,
            "file_type": document.file_type,
            "knowledge_source": source_type,
            "collection": collection or settings.qdrant_collection,
            **document.metadata,
            **(extra_metadata or {}),
        }
        meta["knowledge_source"] = source_type

        # Chunking
        chunks = chunk_text(
            content,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            metadata=meta,
        )

        # Cleaning (after chunking)
        chunks = clean_chunks(chunks)
        if not chunks:
            return {
                "document_id": document_id,
                "chunks_created": 0,
                "status": "empty",
                "knowledge_source": source_type,
                "stages": ["documents", "chunking", "cleaning"],
                "metadata": meta,
            }

        # Embeddings
        embedder = get_embedding_adapter()
        vectors = await embedder.embed_documents([c.content for c in chunks])

        # Vector DB
        ids = [f"{document_id}:{c.index}" for c in chunks]
        payloads = [
            {
                **c.metadata,
                "text": c.content,
                "chunk_index": c.index,
                "knowledge_source": source_type,
            }
            for c in chunks
        ]
        store = get_vector_store()
        await store.upsert(ids=ids, vectors=vectors, payloads=payloads)

        logger.info(
            "rag_ingest_complete",
            document_id=document_id,
            chunks=len(chunks),
            knowledge_source=source_type,
            store=type(store).__name__,
        )
        return {
            "document_id": document_id,
            "chunks_created": len(chunks),
            "status": "indexed",
            "knowledge_source": source_type,
            "stages": ["documents", "chunking", "cleaning", "embeddings", "vector_db"],
            "metadata": meta,
        }

    async def ingest_text(
        self,
        *,
        title: str,
        content: str,
        source: str | None = None,
        file_type: str | None = None,
        collection: str | None = None,
        metadata: dict[str, Any] | None = None,
        knowledge_source: str | None = None,
    ) -> dict[str, Any]:
        doc = load_markdown(
            content,
            title=title,
            source=source or title,
        )
        if file_type:
            doc.file_type = file_type
        return await self.ingest_document(
            doc,
            collection=collection,
            extra_metadata=metadata,
            knowledge_source=knowledge_source,
        )

    async def ingest_upload(
        self,
        *,
        filename: str,
        data: bytes,
        content_type: str | None = None,
        collection: str | None = None,
        metadata: dict[str, Any] | None = None,
        knowledge_source: str | None = None,
    ) -> dict[str, Any]:
        doc = load_bytes(data, filename=filename, content_type=content_type)
        return await self.ingest_document(
            doc,
            collection=collection,
            extra_metadata=metadata,
            knowledge_source=knowledge_source,
        )

    # ------------------------------------------------------------------
    # Query: Retriever → LLM → Answer
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        knowledge_source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retriever stage against the Vector DB."""
        settings = get_settings()
        k = top_k or settings.retrieval_top_k
        embedder = get_embedding_adapter()
        vector = await embedder.embed_query(query)
        store = get_vector_store()

        search_filters = dict(filters or {})
        if knowledge_source:
            search_filters["knowledge_source"] = knowledge_source

        try:
            hits = await store.search(vector, top_k=k, filters=search_filters or None)
        except Exception as exc:
            RAG_RETRIEVALS_TOTAL.labels(store=type(store).__name__, status="error").inc()
            logger.warning("rag_retrieve_failed", error=str(exc))
            return []

        RAG_RETRIEVALS_TOTAL.labels(store=type(store).__name__, status="ok").inc()
        citations: list[dict[str, Any]] = []
        for hit in hits:
            payload = hit.get("payload") or {}
            citations.append(
                {
                    "source": payload.get("source") or payload.get("title") or "knowledge",
                    "knowledge_source": payload.get("knowledge_source"),
                    "chunk_id": hit.get("id"),
                    "score": hit.get("score"),
                    "excerpt": (payload.get("text") or "")[:400],
                    "metadata": {
                        "title": payload.get("title"),
                        "document_id": payload.get("document_id"),
                        "file_type": payload.get("file_type"),
                        "chunk_index": payload.get("chunk_index"),
                        "knowledge_source": payload.get("knowledge_source"),
                    },
                }
            )
        return citations

    async def answer(
        self,
        query: str,
        *,
        top_k: int | None = None,
        knowledge_source: str | None = None,
        language: str = "en",
    ) -> dict[str, Any]:
        """Retriever → LLM → Answer."""
        citations = await self.retrieve(
            query, top_k=top_k, knowledge_source=knowledge_source
        )
        if not citations:
            return {
                "query": query,
                "answer": "I couldn't find matching knowledge to answer that yet.",
                "citations": [],
                "stages": ["retriever", "llm", "answer"],
                "llm_used": False,
                "confidence": 0.3,
            }

        context = "\n\n".join(
            f"[{i+1}] ({c.get('knowledge_source') or 'knowledge'}) "
            f"{c.get('source')}: {c.get('excerpt')}"
            for i, c in enumerate(citations[:5])
        )
        system = (
            "You are a customer support knowledge assistant. "
            "Answer using ONLY the retrieved context. "
            "If the context is insufficient, say so briefly. "
            f"Respond in language code: {language}."
        )
        user = f"Question: {query}\n\nRetrieved context:\n{context}"

        llm = get_llm_adapter()
        llm_used = not isinstance(llm, StubLLMAdapter)
        if llm_used:
            response = await llm.complete(
                [
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ]
            )
            answer_text = response.content
        else:
            # Offline / stub: grounded extractive answer from top chunks
            answer_text = (
                "Based on our knowledge base:\n\n"
                + "\n\n".join(
                    f"• {c.get('excerpt')}" for c in citations[:3] if c.get("excerpt")
                )
            )

        top_score = float(citations[0].get("score") or 0.0)
        confidence = 0.85 if citations else 0.3
        if top_score >= 0.5:
            confidence = min(0.95, max(confidence, top_score))

        return {
            "query": query,
            "answer": answer_text,
            "citations": citations,
            "stages": ["retriever", "llm", "answer"],
            "pipeline": PIPELINE_STAGES,
            "knowledge_sources": KNOWLEDGE_SOURCES,
            "llm_used": llm_used,
            "confidence": confidence,
        }


rag_pipeline = RAGPipeline()
