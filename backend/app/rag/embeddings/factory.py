"""Embedding adapters: OpenAI text embeddings, BGE Large, E5 Large, Sentence Transformers."""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.embeddings.base import BaseEmbeddingAdapter, EmbeddingProvider

logger = get_logger(__name__)

# Catalog aligned to product stack
EMBEDDING_CATALOG: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI text embeddings",
        "default_model": "text-embedding-3-large",
        "alt_models": ["text-embedding-3-small", "text-embedding-ada-002"],
        "typical_dimension": 3072,
    },
    "bge": {
        "label": "BGE Large",
        "default_model": "BAAI/bge-large-en-v1.5",
        "typical_dimension": 1024,
    },
    "e5": {
        "label": "E5 Large",
        "default_model": "intfloat/e5-large-v2",
        "typical_dimension": 1024,
    },
    "sentence_transformers": {
        "label": "Sentence Transformers",
        "default_model": "sentence-transformers/all-mpnet-base-v2",
        "alt_models": ["sentence-transformers/all-MiniLM-L6-v2"],
        "typical_dimension": 768,
    },
}


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashEmbeddingAdapter(BaseEmbeddingAdapter):
    """Offline deterministic embeddings when API keys / local models are unavailable."""

    provider = EmbeddingProvider.SENTENCE_TRANSFORMERS

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        seed = digest
        while len(values) < self.dimension:
            for i in range(0, len(seed) - 3, 4):
                (n,) = struct.unpack_from(">i", seed, i)
                values.append((n % 10000) / 10000.0 - 0.5)
                if len(values) >= self.dimension:
                    break
            seed = hashlib.sha256(seed + text.encode("utf-8")).digest()
        for token in text.lower().split()[:64]:
            th = hashlib.md5(token.encode("utf-8")).digest()
            idx = th[0] % self.dimension
            values[idx] += (th[1] / 255.0) * 0.1
        return _normalize(values[: self.dimension])

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """OpenAI text embeddings (text-embedding-3-large / 3-small / ada-002)."""

    provider = EmbeddingProvider.OPENAI

    def __init__(self, api_key: str, model: str, dimension: int = 3072) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        # text-embedding-3-small defaults to 1536; large to 3072
        if "small" in model:
            self.dimension = min(dimension, 1536) if dimension else 1536
        elif "ada" in model:
            self.dimension = 1536
        else:
            self.dimension = dimension or 3072

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        kwargs: dict[str, Any] = {"model": self.model, "input": texts}
        # Dimension reduction supported on text-embedding-3-* 
        if self.model.startswith("text-embedding-3"):
            kwargs["dimensions"] = self.dimension
        response = await self.client.embeddings.create(**kwargs)
        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0]


class LocalModelEmbeddingAdapter(BaseEmbeddingAdapter):
    """BGE Large / E5 Large / Sentence Transformers via sentence-transformers."""

    def __init__(self, model_name: str, provider: EmbeddingProvider) -> None:
        self.model_name = model_name
        self.provider = provider
        self._model: Any = None
        self.dimension = EMBEDDING_CATALOG.get(provider.value, {}).get(
            "typical_dimension", 768
        )

    def _ensure(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading_embedding_model", model=self.model_name, provider=self.provider.value)
            self._model = SentenceTransformer(self.model_name)
            self.dimension = int(self._model.get_sentence_embedding_dimension())
        return self._model

    def _prep_documents(self, texts: list[str]) -> list[str]:
        if self.provider == EmbeddingProvider.E5:
            return [t if t.startswith("passage:") else f"passage: {t}" for t in texts]
        if self.provider == EmbeddingProvider.BGE:
            # BGE retrieval docs are used as-is; queries get instruction prefix
            return texts
        return texts

    def _prep_query(self, text: str) -> str:
        if self.provider == EmbeddingProvider.E5:
            return text if text.startswith("query:") else f"query: {text}"
        if self.provider == EmbeddingProvider.BGE:
            return f"Represent this sentence for searching relevant passages: {text}"
        return text

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        model = self._ensure()
        prepared = self._prep_documents(texts)
        vectors = await asyncio.to_thread(
            model.encode, prepared, normalize_embeddings=True
        )
        return [v.tolist() for v in vectors]

    async def embed_query(self, text: str) -> list[float]:
        import asyncio

        model = self._ensure()
        prepared = self._prep_query(text)
        vector = await asyncio.to_thread(
            model.encode, prepared, normalize_embeddings=True
        )
        return vector.tolist()


_ADAPTER: BaseEmbeddingAdapter | None = None
_ADAPTER_KEY: str | None = None


def list_embedding_providers() -> list[dict[str, Any]]:
    """Public catalog: OpenAI text embeddings, BGE Large, E5 Large, Sentence Transformers."""
    settings = get_settings()
    models = {
        "openai": settings.openai_embedding_model,
        "bge": settings.bge_model_name,
        "e5": settings.e5_model_name,
        "sentence_transformers": settings.sentence_transformer_model,
    }
    return [
        {
            "id": key,
            **meta,
            "configured_model": models[key],
            "active": (settings.default_embedding_provider == key),
        }
        for key, meta in EMBEDDING_CATALOG.items()
    ]


def get_embedding_adapter(
    provider: str | None = None, *, force_new: bool = False
) -> BaseEmbeddingAdapter:
    """
    Resolve embedding backend.

    Use:
      - openai → OpenAI text embeddings
      - bge → BGE Large
      - e5 → E5 Large
      - sentence_transformers → Sentence Transformers

    Falls back to deterministic hash embeddings offline.
    """
    global _ADAPTER, _ADAPTER_KEY
    settings = get_settings()
    chosen = (provider or settings.default_embedding_provider or "openai").lower()
    cache_key = f"{chosen}:{settings.openai_embedding_model}:{settings.bge_model_name}:{settings.e5_model_name}:{settings.sentence_transformer_model}"

    if not force_new and _ADAPTER is not None and _ADAPTER_KEY == cache_key and provider is None:
        return _ADAPTER

    adapter: BaseEmbeddingAdapter

    if chosen == "openai":
        if settings.openai_api_key:
            adapter = OpenAIEmbeddingAdapter(
                api_key=settings.openai_api_key,
                model=settings.openai_embedding_model,
                dimension=settings.embedding_dimension,
            )
        else:
            logger.warning("openai_embeddings_missing_key_using_hash_stub")
            adapter = HashEmbeddingAdapter(dimension=384)
    elif chosen == "bge":
        try:
            adapter = LocalModelEmbeddingAdapter(
                settings.bge_model_name, EmbeddingProvider.BGE
            )
        except Exception as exc:
            logger.warning("bge_unavailable_using_hash_stub", error=str(exc))
            adapter = HashEmbeddingAdapter(dimension=1024)
    elif chosen == "e5":
        try:
            adapter = LocalModelEmbeddingAdapter(
                settings.e5_model_name, EmbeddingProvider.E5
            )
        except Exception as exc:
            logger.warning("e5_unavailable_using_hash_stub", error=str(exc))
            adapter = HashEmbeddingAdapter(dimension=1024)
    elif chosen in {"sentence_transformers", "st", "sentence-transformers"}:
        try:
            adapter = LocalModelEmbeddingAdapter(
                settings.sentence_transformer_model,
                EmbeddingProvider.SENTENCE_TRANSFORMERS,
            )
        except Exception as exc:
            logger.warning("sentence_transformers_unavailable_using_hash_stub", error=str(exc))
            adapter = HashEmbeddingAdapter(dimension=768)
    else:
        adapter = HashEmbeddingAdapter(dimension=384)

    if provider is None:
        _ADAPTER = adapter
        _ADAPTER_KEY = cache_key
    return adapter


def reset_embedding_adapter() -> None:
    global _ADAPTER, _ADAPTER_KEY
    _ADAPTER = None
    _ADAPTER_KEY = None
