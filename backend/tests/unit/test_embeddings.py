"""Embedding + vector store catalog tests."""

from app.rag.embeddings.factory import (
    EMBEDDING_CATALOG,
    get_embedding_adapter,
    list_embedding_providers,
    reset_embedding_adapter,
)
from app.rag.vectorstores.factory import VECTOR_STORE_CATALOG, list_vector_stores


def test_embedding_catalog_has_required_providers():
    assert set(EMBEDDING_CATALOG) == {
        "openai",
        "bge",
        "e5",
        "sentence_transformers",
    }
    assert "OpenAI" in EMBEDDING_CATALOG["openai"]["label"]
    assert "BGE Large" in EMBEDDING_CATALOG["bge"]["label"]
    assert "E5 Large" in EMBEDDING_CATALOG["e5"]["label"]
    assert "Sentence Transformers" in EMBEDDING_CATALOG["sentence_transformers"]["label"]


def test_vector_store_catalog_has_required_backends():
    assert set(VECTOR_STORE_CATALOG) == {"qdrant", "pinecone", "chroma"}


def test_list_helpers():
    emb = list_embedding_providers()
    stores = list_vector_stores()
    assert len(emb) == 4
    assert len(stores) == 3
    assert {e["id"] for e in emb} == set(EMBEDDING_CATALOG)
    assert {s["id"] for s in stores} == set(VECTOR_STORE_CATALOG)


def test_openai_without_key_falls_back_to_hash(monkeypatch):
    reset_embedding_adapter()
    monkeypatch.setenv("DEFAULT_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    adapter = get_embedding_adapter(force_new=True)
    # Hash stub used offline
    assert getattr(adapter, "dimension", 0) == 384
    get_settings.cache_clear()
    reset_embedding_adapter()
