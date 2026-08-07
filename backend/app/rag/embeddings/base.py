"""Embedding adapter protocol — OpenAI / BGE / E5 / SentenceTransformers."""

from abc import ABC, abstractmethod
from enum import Enum


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    BGE = "bge"
    E5 = "e5"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class BaseEmbeddingAdapter(ABC):
    provider: EmbeddingProvider
    dimension: int

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        ...
