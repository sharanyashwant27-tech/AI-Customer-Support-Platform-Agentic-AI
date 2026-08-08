"""Ticket service unit tests."""

from __future__ import annotations

import pytest

from app.db.models.ticket import TicketPriority
from app.services.ticket_service import (
    extract_ticket_draft,
    map_priority,
    persist_agent_ticket_draft,
)


def test_map_priority_p1_to_urgent():
    assert map_priority("P1") == TicketPriority.URGENT
    assert map_priority("high") == TicketPriority.HIGH


def test_extract_ticket_draft_from_agent():
    draft = extract_ticket_draft(
        {
            "ticket": {
                "data": {
                    "ticket_draft": {
                        "ticket_number": "TKT-ABC",
                        "subject": "Help",
                        "description": "Need help",
                        "action": "create",
                        "should_create": True,
                        "priority": "P2",
                        "db_priority": "high",
                    }
                }
            }
        }
    )
    assert draft is not None
    assert draft["ticket_number"] == "TKT-ABC"


@pytest.mark.asyncio
async def test_persist_ticket_draft_without_db():
    ticket = await persist_agent_ticket_draft(
        {
            "ticket_number": "TKT-TEST01",
            "subject": "Delay",
            "description": "Package late",
            "action": "create",
            "should_create": True,
            "priority": "P1",
            "db_priority": "urgent",
        },
        db=None,
    )
    assert ticket is not None
    assert ticket.ticket_number == "TKT-TEST01"
    assert ticket.priority == TicketPriority.URGENT


@pytest.mark.asyncio
async def test_close_ticket_without_db():
    from app.services.ticket_service import close_ticket, create_ticket
    from app.db.models.ticket import TicketStatus

    created = await create_ticket(
        subject="Temp",
        description="Will close",
        ticket_number="TKT-CLOSE01",
        db=None,
    )
    from app.api.v1.endpoints import tickets as tickets_ep

    tickets_ep._FALLBACK[str(created.id)] = created
    closed = await close_ticket("TKT-CLOSE01", db=None, status=TicketStatus.RESOLVED)
    assert closed is not None
    assert closed.status == TicketStatus.RESOLVED
