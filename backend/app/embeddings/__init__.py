"""Alias package — embeddings live under `app.rag.embeddings`."""

from app.rag.embeddings.factory import (
    EMBEDDING_CATALOG,
    get_embedding_adapter,
    list_embedding_providers,
    reset_embedding_adapter,
)

__all__ = [
    "EMBEDDING_CATALOG",
    "get_embedding_adapter",
    "list_embedding_providers",
    "reset_embedding_adapter",
]
