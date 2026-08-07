"""Pydantic schemas for orders, knowledge, and feedback."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OrderLookupRequest(BaseModel):
    order_id: str | None = None
    email: str | None = None
    tracking_number: str | None = None


class OrderItem(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price: float


class OrderResponse(BaseModel):
    order_id: str
    status: str
    customer_email: str
    items: list[OrderItem]
    total: float
    currency: str = "USD"
    placed_at: datetime
    estimated_delivery: datetime | None = None
    tracking_number: str | None = None
    shipping_address: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIngestRequest(BaseModel):
    title: str
    content: str | None = None
    source_url: str | None = None
    file_type: str | None = None
    knowledge_source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    collection: str | None = None


class KnowledgeIngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    status: str
    knowledge_source: str | None = None
    stages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = None
    category: str | None = None
    session_id: str | None = None
    chat_history_id: UUID | None = None
    customer_id: UUID | None = None
    agent_name: str | None = None
    # Legacy aliases
    conversation_id: UUID | None = None
    message_id: UUID | None = None


class FeedbackResponse(BaseModel):
    id: UUID
    rating: int
    comment: str | None = None
    category: str | None = None
    session_id: str | None = None
    chat_history_id: UUID | None = None
    customer_id: UUID | None = None
    agent_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    services: dict[str, str] = Field(default_factory=dict)
