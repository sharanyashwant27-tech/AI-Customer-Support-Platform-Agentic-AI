"""Alias package — vector DB adapters live under `app.rag.vectorstores`."""

from app.rag.vectorstores.factory import (
    VECTOR_STORE_CATALOG,
    get_vector_store,
    list_vector_stores,
    reset_vector_store,
)

__all__ = [
    "VECTOR_STORE_CATALOG",
    "get_vector_store",
    "list_vector_stores",
    "reset_vector_store",
]
