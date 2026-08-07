"""Agent ORM model — PostgreSQL `agents` table (AI + human specialists)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AgentKind(str, enum.Enum):
    AI = "ai"
    HUMAN = "human"
    SYSTEM = "system"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[AgentKind] = mapped_column(
        Enum(AgentKind, name="agent_kind"), default=AgentKind.AI
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tickets = relationship(
        "Ticket",
        back_populates="assigned_agent",
        lazy="select",
        foreign_keys="Ticket.assigned_agent_id",
    )
