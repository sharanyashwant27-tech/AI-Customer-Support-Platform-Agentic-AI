"""Pydantic schemas for tickets."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models.ticket import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    priority: TicketPriority = TicketPriority.MEDIUM
    category: str | None = None


class TicketUpdate(BaseModel):
    subject: str | None = None
    description: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: str | None = None
    assigned_agent_id: UUID | None = None


class TicketResponse(BaseModel):
    id: UUID
    ticket_number: str
    customer_id: UUID
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    assigned_agent_id: UUID | None = None
    category: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
