"""Pydantic schemas for chat API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str
    chunk_id: str | None = None
    score: float | None = None
    excerpt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    channel: str = "web"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    session_id: str
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    reply: str
    intent: str | None = None
    confidence: float | None = None
    agent_name: str | None = None
    agents_used: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    handoff_required: bool = False
    sentiment: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    language: str | None = "en"
    channel: str | None = "web"
    created_at: datetime | None = None
