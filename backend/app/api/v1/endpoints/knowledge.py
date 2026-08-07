"""Knowledge ingestion + RAG answer API."""

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile

from app.rag.pipeline import PIPELINE_STAGES, rag_pipeline
from app.rag.sources import KNOWLEDGE_SOURCES
from app.schemas.common import KnowledgeIngestRequest, KnowledgeIngestResponse

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/sources")
async def list_knowledge_sources() -> dict[str, Any]:
    return {
        "sources": KNOWLEDGE_SOURCES,
        "pipeline": PIPELINE_STAGES,
    }


@router.get("/backends")
async def list_rag_backends() -> dict[str, Any]:
    """Embeddings + vector DB options (OpenAI/BGE/E5/ST → Qdrant/Pinecone/Chroma)."""
    from app.core.config import get_settings
    from app.rag.embeddings.factory import list_embedding_providers
    from app.rag.vectorstores.factory import list_vector_stores

    settings = get_settings()
    return {
        "embeddings": list_embedding_providers(),
        "vector_stores": list_vector_stores(),
        "active": {
            "embedding_provider": settings.default_embedding_provider,
            "vector_store": settings.vector_store,
        },
    }


@router.post("/ingest", response_model=KnowledgeIngestResponse)
@router.post("/index", response_model=KnowledgeIngestResponse)
async def ingest_document(payload: KnowledgeIngestRequest) -> KnowledgeIngestResponse:
    result = await rag_pipeline.ingest_text(
        title=payload.title,
        content=payload.content or "",
        source=payload.source_url or payload.title,
        file_type=payload.file_type,
        collection=payload.collection,
        metadata=payload.metadata,
        knowledge_source=payload.knowledge_source,
    )
    return KnowledgeIngestResponse(
        document_id=result["document_id"],
        chunks_created=result["chunks_created"],
        status=result["status"],
        knowledge_source=result.get("knowledge_source"),
        stages=result.get("stages") or [],
        metadata=result.get("metadata") or {},
    )


@router.post("/ingest/upload", response_model=KnowledgeIngestResponse)
async def ingest_upload(
    file: Annotated[UploadFile, File(...)],
    collection: Annotated[str | None, Form()] = None,
    knowledge_source: Annotated[str | None, Form()] = None,
) -> KnowledgeIngestResponse:
    data = await file.read()
    result = await rag_pipeline.ingest_upload(
        filename=file.filename or "upload",
        data=data,
        content_type=file.content_type,
        collection=collection,
        knowledge_source=knowledge_source,
    )
    return KnowledgeIngestResponse(
        document_id=result["document_id"],
        chunks_created=result["chunks_created"],
        status=result["status"],
        knowledge_source=result.get("knowledge_source"),
        stages=result.get("stages") or [],
        metadata=result.get("metadata") or {},
    )


@router.post("/search")
async def search_knowledge(payload: dict) -> dict:
    """Retriever stage only."""
    query = str(payload.get("query") or "")
    top_k = int(payload.get("top_k") or 5)
    knowledge_source = payload.get("knowledge_source")
    citations = await rag_pipeline.retrieve(
        query,
        top_k=top_k,
        knowledge_source=str(knowledge_source) if knowledge_source else None,
    )
    return {
        "query": query,
        "results": citations,
        "stages": ["retriever"],
        "pipeline": PIPELINE_STAGES,
    }


@router.post("/answer")
async def answer_knowledge(payload: dict) -> dict:
    """Retriever → LLM → Answer."""
    query = str(payload.get("query") or "")
    top_k = payload.get("top_k")
    knowledge_source = payload.get("knowledge_source")
    language = str(payload.get("language") or "en")
    return await rag_pipeline.answer(
        query,
        top_k=int(top_k) if top_k else None,
        knowledge_source=str(knowledge_source) if knowledge_source else None,
        language=language,
    )
