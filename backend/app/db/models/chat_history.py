"""Chat history ORM — PostgreSQL `chat_history` table."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ChatRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    AGENT = "agent"


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole, name="chat_role"))
    content: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(50), default="web")
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ticket_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    citations: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    customer = relationship("Customer", back_populates="chat_history")
