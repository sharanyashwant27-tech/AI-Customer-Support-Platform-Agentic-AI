"""Public REST API contract.

POST /chat
POST /ticket
GET  /ticket/{id}
GET  /orders/{id}
POST /upload
POST /knowledge/index
GET  /customer/{id}
POST /feedback
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, get_db_optional
from app.api.v1.endpoints import customers as customers_ep
from app.api.v1.endpoints import feedback as feedback_ep
from app.api.v1.endpoints import orders as orders_ep
from app.api.v1.endpoints import tickets as tickets_ep
from app.db.models.user import User
from app.db.repositories.entities import knowledge_doc_repo
from app.rag.pipeline import rag_pipeline
from app.rag.sources import infer_knowledge_source
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.schemas.common import (
    FeedbackCreate,
    FeedbackResponse,
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    OrderResponse,
)
from app.schemas.ticket import TicketCreate, TicketResponse
from app.services.chat_service import chat_service

router = APIRouter(tags=["REST API"])


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatMessageResponse)
async def post_chat(
    payload: ChatMessageRequest,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> ChatMessageResponse:
    """Send a customer chat message through the Master Agent."""
    customer_id = None
    if user:
        customer_id = str(user.customer_id or user.id)
    return await chat_service.handle_message(payload, customer_id=customer_id, db=db)


# ---------------------------------------------------------------------------
# POST /ticket  ·  GET /ticket/{id}
# ---------------------------------------------------------------------------


@router.post("/ticket", response_model=TicketResponse, status_code=201)
async def post_ticket(
    payload: TicketCreate,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> TicketResponse:
    """Create a support ticket."""
    return await tickets_ep.create_ticket(payload, user, db)


@router.get("/ticket/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: str,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> TicketResponse:
    """Fetch a ticket by id or ticket number."""
    # Prefer UUID lookup; fall back to ticket_number scan via list
    try:
        return await tickets_ep.get_ticket(ticket_id, db)
    except HTTPException:
        if db is not None:
            from sqlalchemy import select

            from app.db.models.ticket import Ticket

            result = await db.execute(
                select(Ticket).where(Ticket.ticket_number == ticket_id.upper())
            )
            ticket = result.scalar_one_or_none()
            if ticket:
                return tickets_ep._to_response(ticket)
        raise


# ---------------------------------------------------------------------------
# GET /orders/{id}
# ---------------------------------------------------------------------------


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    """Fetch an order by order id (e.g. ORD-1001)."""
    return await orders_ep.get_order(order_id)


# ---------------------------------------------------------------------------
# POST /upload  ·  POST /knowledge/index
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=KnowledgeIngestResponse)
async def post_upload(
    file: Annotated[UploadFile, File(...)],
    collection: Annotated[str | None, Form()] = None,
    knowledge_source: Annotated[str | None, Form()] = None,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)] = None,
) -> KnowledgeIngestResponse:
    """Upload a knowledge file (PDF/DOCX/HTML/MD/email) into the RAG pipeline."""
    data = await file.read()
    filename = file.filename or "upload"
    result = await rag_pipeline.ingest_upload(
        filename=filename,
        data=data,
        content_type=file.content_type,
        collection=collection,
        knowledge_source=knowledge_source
        or infer_knowledge_source(filename=filename, file_type=file.content_type),
    )
    if db is not None:
        try:
            await knowledge_doc_repo.create(
                db,
                title=filename,
                source=filename,
                content=f"[uploaded binary {len(data)} bytes]",
                knowledge_source=result.get("knowledge_source") or "knowledge_base",
                file_type=file.content_type,
                chunk_count=int(result.get("chunks_created") or 0),
                document_id=result.get("document_id"),
                metadata=result.get("metadata") or {},
            )
        except Exception:
            pass
    return KnowledgeIngestResponse(
        document_id=result["document_id"],
        chunks_created=result["chunks_created"],
        status=result["status"],
        knowledge_source=result.get("knowledge_source"),
        stages=result.get("stages") or [],
        metadata=result.get("metadata") or {},
    )


@router.post("/knowledge/index", response_model=KnowledgeIngestResponse)
async def post_knowledge_index(
    payload: KnowledgeIngestRequest,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)] = None,
) -> KnowledgeIngestResponse:
    """Index text into the knowledge base (Documents → … → Vector DB)."""
    result = await rag_pipeline.ingest_text(
        title=payload.title,
        content=payload.content or "",
        source=payload.source_url or payload.title,
        file_type=payload.file_type,
        collection=payload.collection,
        metadata=payload.metadata,
        knowledge_source=payload.knowledge_source,
    )
    if db is not None:
        try:
            await knowledge_doc_repo.create(
                db,
                title=payload.title,
                source=payload.source_url or payload.title,
                content=payload.content or "",
                knowledge_source=result.get("knowledge_source") or "knowledge_base",
                file_type=payload.file_type,
                chunk_count=int(result.get("chunks_created") or 0),
                document_id=result.get("document_id"),
                metadata=result.get("metadata") or {},
            )
        except Exception:
            pass
    return KnowledgeIngestResponse(
        document_id=result["document_id"],
        chunks_created=result["chunks_created"],
        status=result["status"],
        knowledge_source=result.get("knowledge_source"),
        stages=result.get("stages") or [],
        metadata=result.get("metadata") or {},
    )


# ---------------------------------------------------------------------------
# GET /customer/{id}
# ---------------------------------------------------------------------------


@router.get("/customer/{customer_id}")
async def get_customer(
    customer_id: str,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> dict[str, Any]:
    """Customer profile, chat history, orders, and tickets."""
    return await customers_ep.customer_history(customer_id, db)


# ---------------------------------------------------------------------------
# POST /feedback
# ---------------------------------------------------------------------------


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def post_feedback(
    payload: FeedbackCreate,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> FeedbackResponse:
    """Submit CSAT / prompt-optimization feedback."""
    return await feedback_ep.submit_feedback(payload, db)
