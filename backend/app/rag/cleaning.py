"""Cleaning stage — runs after chunking, before embeddings."""

from __future__ import annotations

import re
import unicodedata

from app.rag.chunking.splitter import TextChunk


def clean_document_text(text: str) -> str:
    """Normalize raw document text before / during load."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def clean_chunk_text(text: str) -> str:
    """Clean a single chunk prior to embedding."""
    text = clean_document_text(text)
    # Drop leftover markdown noise that hurts embeddings
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`]{1,3}", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def clean_chunks(chunks: list[TextChunk]) -> list[TextChunk]:
    """Pipeline stage: Chunking → Cleaning."""
    cleaned: list[TextChunk] = []
    for chunk in chunks:
        content = clean_chunk_text(chunk.content)
        if not content or len(content) < 20:
            continue
        cleaned.append(
            TextChunk(
                content=content,
                index=len(cleaned),
                metadata={**chunk.metadata, "cleaned": True},
            )
        )
    return cleaned
