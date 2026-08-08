"""Support ticket creation and persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.ticket import TicketPriority, TicketStatus
from app.db.repositories.entities import customer_repo, ticket_repo
from app.schemas.ticket import TicketResponse

logger = get_logger(__name__)

_PRIORITY_MAP = {
    "P1": TicketPriority.URGENT,
    "P2": TicketPriority.HIGH,
    "P3": TicketPriority.MEDIUM,
    "urgent": TicketPriority.URGENT,
    "high": TicketPriority.HIGH,
    "medium": TicketPriority.MEDIUM,
    "low": TicketPriority.LOW,
}


def map_priority(raw: str | None) -> TicketPriority:
    if not raw:
        return TicketPriority.MEDIUM
    key = str(raw).strip()
    return _PRIORITY_MAP.get(key) or _PRIORITY_MAP.get(key.lower()) or TicketPriority.MEDIUM


async def create_ticket(
    *,
    subject: str,
    description: str,
    priority: TicketPriority | str = TicketPriority.MEDIUM,
    category: str | None = None,
    ticket_number: str | None = None,
    db: AsyncSession | None = None,
    customer_id: str | None = None,
    customer_email: str | None = None,
    customer_name: str | None = None,
) -> TicketResponse:
    """Create a ticket in PostgreSQL when available, else in-memory response."""
    if not isinstance(priority, TicketPriority):
        priority = map_priority(str(priority))

    if db is not None:
        try:
            cust_uuid: uuid.UUID | None = None
            if customer_id:
                try:
                    cust_uuid = uuid.UUID(str(customer_id))
                except ValueError:
                    cust_uuid = None
            if cust_uuid is None:
                email = customer_email or f"guest-{uuid.uuid4().hex[:8]}@aics.local"
                customer = await customer_repo.get_or_create(
                    db,
                    email=email,
                    full_name=customer_name or "Guest",
                    external_id=str(customer_id) if customer_id else None,
                )
                cust_uuid = customer.id
            ticket = await ticket_repo.create(
                db,
                customer_id=cust_uuid,
                subject=subject[:500],
                description=description,
                priority=priority,
                category=category,
                ticket_number=ticket_number,
            )
            await db.flush()
            return TicketResponse.model_validate(ticket)
        except Exception as exc:
            logger.warning("ticket_db_persist_failed", error=str(exc))
            try:
                await db.rollback()
            except Exception:
                pass

    now = datetime.now(UTC)
    return TicketResponse(
        id=uuid.uuid4(),
        ticket_number=ticket_number or f"TKT-{uuid.uuid4().hex[:8].upper()}",
        customer_id=uuid.uuid4(),
        subject=subject[:500],
        description=description,
        status=TicketStatus.OPEN,
        priority=priority,
        category=category,
        created_at=now,
        updated_at=now,
    )


async def close_ticket(
    ticket_ref: str,
    *,
    db: AsyncSession | None = None,
    status: TicketStatus = TicketStatus.CLOSED,
) -> TicketResponse | None:
    """Close or resolve a ticket by UUID or TKT- number."""
    ticket_ref = ticket_ref.strip()
    if db is not None:
        try:
            row = None
            try:
                row = await ticket_repo.get(db, uuid.UUID(ticket_ref))
            except ValueError:
                row = None
            if row is None and ticket_ref.upper().startswith("TKT-"):
                row = await ticket_repo.get_by_number(db, ticket_ref)
            if row is None:
                # also try uppercase lookup for bare numbers
                row = await ticket_repo.get_by_number(db, ticket_ref)
            if row is not None:
                updated = await ticket_repo.update(db, row, status=status)
                return TicketResponse.model_validate(updated)
        except Exception as exc:
            logger.warning("ticket_close_db_failed", error=str(exc), ref=ticket_ref)
            try:
                await db.rollback()
            except Exception:
                pass

    # In-memory fallback: scan tickets endpoint fallback store
    from app.api.v1.endpoints import tickets as tickets_ep

    for key, item in list(tickets_ep._FALLBACK.items()):
        if str(item.id) == ticket_ref or item.ticket_number.upper() == ticket_ref.upper():
            data = item.model_dump()
            data["status"] = status
            data["updated_at"] = datetime.now(UTC)
            updated = TicketResponse(**data)
            tickets_ep._FALLBACK[key] = updated
            return updated
    return None


async def persist_agent_ticket_draft(
    draft: dict[str, Any],
    *,
    db: AsyncSession | None = None,
    customer_id: str | None = None,
    customer_email: str | None = None,
) -> TicketResponse | None:
    """Persist a Ticket Agent / playbook draft (create, escalate, close, update)."""
    if not draft:
        return None

    action = str(draft.get("action") or "create").lower()
    ticket_number = draft.get("ticket_number")

    if action in {"close", "update"} or draft.get("should_close") or draft.get("should_update"):
        if not ticket_number:
            return None
        target_status = {
            "close": TicketStatus.CLOSED,
            "update": TicketStatus.IN_PROGRESS,
            "escalate": TicketStatus.ESCALATED,
        }.get(action, TicketStatus.CLOSED if draft.get("should_close") else TicketStatus.IN_PROGRESS)
        # Prefer resolved when user said resolved
        desc = str(draft.get("description") or "").lower()
        if action == "close" and "resolved" in desc:
            target_status = TicketStatus.RESOLVED
        closed = await close_ticket(str(ticket_number), db=db, status=target_status)
        if closed:
            logger.info(
                "ticket_status_updated",
                ticket_number=closed.ticket_number,
                status=closed.status.value,
                action=action,
            )
            return closed
        # If ticket didn't exist yet, create then close
        if action == "close":
            created = await create_ticket(
                subject=str(draft.get("subject") or "Support request")[:500],
                description=str(draft.get("description") or "Closed via chat"),
                priority=map_priority(draft.get("db_priority") or draft.get("priority")),
                category=str(draft.get("category")) if draft.get("category") else None,
                ticket_number=str(ticket_number),
                db=db,
                customer_id=customer_id,
                customer_email=customer_email,
            )
            return await close_ticket(
                created.ticket_number, db=db, status=target_status
            ) or created
        return None

    should_create = bool(draft.get("should_create", action in {"create", "escalate"}))
    if not should_create and action not in {"create", "escalate"}:
        return None

    subject = str(draft.get("subject") or "Support request")[:500]
    description = str(draft.get("description") or subject)
    priority = map_priority(draft.get("db_priority") or draft.get("priority"))
    category = draft.get("category")

    ticket = await create_ticket(
        subject=subject,
        description=description,
        priority=priority,
        category=str(category) if category else None,
        ticket_number=str(ticket_number) if ticket_number else None,
        db=db,
        customer_id=customer_id,
        customer_email=customer_email,
    )
    if action == "escalate":
        escalated = await close_ticket(
            ticket.ticket_number, db=db, status=TicketStatus.ESCALATED
        )
        if escalated:
            ticket = escalated
    logger.info(
        "ticket_persisted",
        ticket_number=ticket.ticket_number,
        priority=ticket.priority.value,
        action=action,
    )
    return ticket


def extract_ticket_draft(agent_results: dict[str, Any] | None) -> dict[str, Any] | None:
    if not agent_results:
        return None
    ticket = agent_results.get("ticket") or {}
    data = ticket.get("data") or {}
    draft = data.get("ticket_draft")
    if isinstance(draft, dict):
        return draft

    for key in ("package_delay", "package_delay_workflow"):
        pkg = agent_results.get(key) or {}
        pkg_data = pkg.get("data") or {}
        pkg_ticket = pkg_data.get("ticket")
        if isinstance(pkg_ticket, dict):
            return {
                "ticket_number": pkg_ticket.get("ticket_number"),
                "subject": pkg_ticket.get("subject") or "Package delay",
                "description": pkg_ticket.get("description")
                or pkg_ticket.get("subject")
                or "Package delay",
                "priority": pkg_ticket.get("priority") or "high",
                "category": pkg_ticket.get("category") or "shipping_delay",
                "action": "create",
                "should_create": True,
            }
    return None
