"""RAG pipeline unit tests."""

import pytest

from app.rag.chunking.splitter import chunk_text
from app.rag.pipeline import rag_pipeline
from app.rag.vectorstores.factory import InMemoryVectorStore, reset_vector_store


@pytest.mark.asyncio
async def test_chunk_and_ingest_retrieve(monkeypatch):
    reset_vector_store()
    store = InMemoryVectorStore()
    monkeypatch.setattr(
        "app.rag.pipeline.get_vector_store", lambda force_memory=False: store
    )
    monkeypatch.setattr(
        "app.rag.vectorstores.factory.get_vector_store", lambda force_memory=False: store
    )

    result = await rag_pipeline.ingest_text(
        title="Return Policy",
        content="Customers may return eligible products within 30 days of delivery. "
        "Proof of purchase is required. Digital goods are non-refundable.",
        source="return_policy.md",
    )
    assert result["chunks_created"] >= 1
    assert result["status"] == "indexed"

    citations = await rag_pipeline.retrieve("What is the return policy window?")
    assert citations
    assert "30 days" in (citations[0].get("excerpt") or "") or citations[0].get("source")


def test_chunk_overlap():
    chunks = chunk_text("a" * 1200, chunk_size=500, chunk_overlap=50)
    assert len(chunks) >= 2
    assert chunks[0].index == 0
