"""Customer history and profile APIs backed by PostgreSQL core tables."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_optional
from app.db.models.chat_history import ChatHistory
from app.db.models.customer import Customer
from app.db.models.order import Order
from app.db.models.ticket import Ticket
from app.db.repositories.entities import customer_repo
from app.memory.conversation import ensure_memory

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/{customer_id}/history")
async def customer_history(
    customer_id: str,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> dict[str, Any]:
    memory = await ensure_memory()
    profile = await memory.get_profile(customer_id)
    long_term = await memory.get_long_term(customer_id)
    purchases = await memory.get_purchase_history(customer_id)
    prefs = await memory.get_preferences(customer_id)

    chat: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    customer_row: dict[str, Any] | None = None

    if db is not None:
        try:
            customer = None
            try:
                cid = UUID(customer_id)
                customer = await customer_repo.get_by_id(db, cid)
            except ValueError:
                customer = await customer_repo.get_by_email(db, customer_id)
                if customer is None:
                    result = await db.execute(
                        select(Customer).where(Customer.external_id == customer_id)
                    )
                    customer = result.scalar_one_or_none()

            if customer:
                customer_row = {
                    "id": str(customer.id),
                    "email": customer.email,
                    "full_name": customer.full_name,
                    "tier": customer.tier,
                    "preferences": customer.preferences,
                }
                cid = customer.id
                chat_rows = await db.execute(
                    select(ChatHistory)
                    .where(ChatHistory.customer_id == cid)
                    .order_by(ChatHistory.created_at.desc())
                    .limit(50)
                )
                chat = [
                    {
                        "session_id": r.session_id,
                        "role": r.role.value,
                        "content": r.content,
                        "intent": r.intent,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in reversed(list(chat_rows.scalars().all()))
                ]
                ticket_rows = await db.execute(
                    select(Ticket)
                    .where(Ticket.customer_id == cid)
                    .order_by(Ticket.created_at.desc())
                    .limit(20)
                )
                tickets = [
                    {
                        "ticket_number": t.ticket_number,
                        "subject": t.subject,
                        "status": t.status.value,
                        "priority": t.priority.value,
                    }
                    for t in ticket_rows.scalars().all()
                ]
                order_rows = await db.execute(
                    select(Order)
                    .where(Order.customer_id == cid)
                    .order_by(Order.placed_at.desc())
                    .limit(20)
                )
                orders = [
                    {
                        "order_number": o.order_number,
                        "status": o.status.value,
                        "total": o.total,
                        "tracking_number": o.tracking_number,
                    }
                    for o in order_rows.scalars().all()
                ]
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "customer_id": customer_id,
        "customer": customer_row,
        "profile": profile,
        "preferences": prefs,
        "purchase_history": purchases,
        "long_term_memory": long_term,
        "chat_history": chat,
        "orders": orders,
        "tickets": tickets,
    }


@router.post("/{customer_id}/memory")
async def remember_fact(customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    fact = payload.get("fact")
    if not fact:
        raise HTTPException(status_code=400, detail="Missing fact")
    memory = await ensure_memory()
    await memory.remember_long_term(customer_id, str(fact))
    if payload.get("profile"):
        await memory.update_profile(customer_id, dict(payload["profile"]))
    if payload.get("preferences"):
        await memory.set_preferences(customer_id, dict(payload["preferences"]))
    return {
        "customer_id": customer_id,
        "long_term_memory": await memory.get_long_term(customer_id),
        "profile": await memory.get_profile(customer_id),
        "preferences": await memory.get_preferences(customer_id),
    }
