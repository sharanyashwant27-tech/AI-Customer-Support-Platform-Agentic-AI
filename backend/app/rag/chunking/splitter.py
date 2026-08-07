"""Simple text chunker used by the knowledge pipeline foundation."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextChunk:
    content: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_text(
    text: str,
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    metadata: dict[str, Any] | None = None,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    cleaned = text.strip()
    if not cleaned:
        return []

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(
                TextChunk(
                    content=piece,
                    index=index,
                    metadata={**(metadata or {}), "start": start, "end": end},
                )
            )
            index += 1
        if end >= len(cleaned):
            break
        start = end - chunk_overlap
    return chunks
