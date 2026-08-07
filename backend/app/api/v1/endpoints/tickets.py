"""Ticket management API with PostgreSQL persistence and memory fallback."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional, get_db_optional
from app.db.models.ticket import TicketStatus
from app.db.models.user import User
from app.db.repositories.entities import customer_repo, ticket_repo
from app.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate

router = APIRouter(prefix="/tickets", tags=["tickets"])

_FALLBACK: dict[str, TicketResponse] = {}


def _to_response(ticket: object) -> TicketResponse:
    return TicketResponse.model_validate(ticket)


async def _resolve_customer_id(
    db: AsyncSession, user: User | None
) -> uuid.UUID:
    if user and user.customer_id:
        return user.customer_id
    email = user.email if user else f"guest-{uuid.uuid4().hex[:8]}@aics.local"
    name = user.full_name if user else "Guest"
    customer = await customer_repo.get_or_create(db, email=email, full_name=name)
    if user and not user.customer_id:
        user.customer_id = customer.id
        await db.flush()
    return customer.id


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> TicketResponse:
    if db is not None:
        try:
            customer_id = await _resolve_customer_id(db, user)
            ticket = await ticket_repo.create(
                db,
                customer_id=customer_id,
                subject=payload.subject,
                description=payload.description,
                priority=payload.priority,
                category=payload.category,
            )
            return _to_response(ticket)
        except Exception:
            pass

    now = datetime.now(UTC)
    customer_id = user.customer_id if user and user.customer_id else uuid.uuid4()
    ticket = TicketResponse(
        id=uuid.uuid4(),
        ticket_number=f"TKT-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer_id,
        subject=payload.subject,
        description=payload.description,
        status=TicketStatus.OPEN,
        priority=payload.priority,
        category=payload.category,
        created_at=now,
        updated_at=now,
    )
    _FALLBACK[str(ticket.id)] = ticket
    return ticket


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    user: Annotated[User | None, Depends(get_current_user_optional)],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> list[TicketResponse]:
    if db is not None:
        try:
            customer_id = None
            if user:
                customer_id = await _resolve_customer_id(db, user)
            tickets = await ticket_repo.list_for_customer(db, customer_id)
            return [_to_response(t) for t in tickets]
        except Exception:
            pass
    tickets = list(_FALLBACK.values())
    if user and user.customer_id:
        tickets = [t for t in tickets if t.customer_id == user.customer_id]
    return tickets


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: str,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> TicketResponse:
    if db is not None:
        try:
            ticket = await ticket_repo.get(db, uuid.UUID(ticket_id))
            if ticket:
                return _to_response(ticket)
        except Exception:
            pass
    fallback = _FALLBACK.get(ticket_id)
    if fallback:
        return fallback
    raise HTTPException(status_code=404, detail="Ticket not found")


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: str,
    payload: TicketUpdate,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> TicketResponse:
    if db is not None:
        try:
            ticket = await ticket_repo.get(db, uuid.UUID(ticket_id))
            if ticket:
                updated = await ticket_repo.update(
                    db, ticket, **payload.model_dump(exclude_unset=True)
                )
                return _to_response(updated)
        except Exception:
            pass
    fallback = _FALLBACK.get(ticket_id)
    if not fallback:
        raise HTTPException(status_code=404, detail="Ticket not found")
    data = fallback.model_dump()
    data.update(payload.model_dump(exclude_unset=True))
    data["updated_at"] = datetime.now(UTC)
    updated = TicketResponse(**data)
    _FALLBACK[ticket_id] = updated
    return updated
