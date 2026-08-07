"""Knowledge source taxonomy for the RAG pipeline."""

from __future__ import annotations

from enum import Enum


class KnowledgeSource(str, Enum):
    """Supported knowledge sources."""

    PDFS = "pdfs"
    PRODUCT_MANUALS = "product_manuals"
    FAQS = "faqs"
    POLICIES = "policies"
    KNOWLEDGE_BASE = "knowledge_base"
    EMAILS = "emails"
    RELEASE_NOTES = "release_notes"
    INTERNAL_DOCUMENTATION = "internal_documentation"


KNOWLEDGE_SOURCES = [s.value for s in KnowledgeSource]

# Filename / path hints → source type
_SOURCE_HINTS: list[tuple[str, KnowledgeSource]] = [
    ("faq", KnowledgeSource.FAQS),
    ("manual", KnowledgeSource.PRODUCT_MANUALS),
    ("policy", KnowledgeSource.POLICIES),
    ("policies", KnowledgeSource.POLICIES),
    ("release", KnowledgeSource.RELEASE_NOTES),
    ("changelog", KnowledgeSource.RELEASE_NOTES),
    ("email", KnowledgeSource.EMAILS),
    ("internal", KnowledgeSource.INTERNAL_DOCUMENTATION),
    ("sop", KnowledgeSource.INTERNAL_DOCUMENTATION),
    ("kb_", KnowledgeSource.KNOWLEDGE_BASE),
    ("knowledge_base", KnowledgeSource.KNOWLEDGE_BASE),
    ("knowledge-base", KnowledgeSource.KNOWLEDGE_BASE),
    ("pdf", KnowledgeSource.PDFS),
]


def infer_knowledge_source(
    *,
    filename: str | None = None,
    file_type: str | None = None,
    explicit: str | None = None,
) -> str:
    """Resolve knowledge_source label for indexing / filtering."""
    if explicit:
        normalized = explicit.strip().lower().replace(" ", "_").replace("-", "_")
        for source in KnowledgeSource:
            if source.value == normalized or source.name.lower() == normalized:
                return source.value
        return normalized

    name = (filename or "").lower()
    for hint, source in _SOURCE_HINTS:
        if hint in name:
            return source.value

    if (file_type or "").lower() == "pdf" or name.endswith(".pdf"):
        return KnowledgeSource.PDFS.value

    return KnowledgeSource.KNOWLEDGE_BASE.value
