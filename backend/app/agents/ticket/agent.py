"""Ticket Agent — create, update, close, escalate with P1/P2/P3 auto-priority."""

from __future__ import annotations

import re
import uuid

from app.advanced.features import auto_priority, register_sla, summarize_ticket
from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent


class TicketManagementAgent(BaseAgent):
    """Automatically creates, updates, closes, or escalates tickets."""

    name = AgentName.TICKET

    def _detect_action(self, message: str, intent: str, sentiment: str) -> str:
        lower = message.lower()
        if re.search(r"\b(close|resolved|solved|all good)\b", lower):
            return "close"
        if re.search(r"\b(escalat|manager|supervisor|human)\b", lower) or sentiment in {
            "angry",
            "urgent",
        }:
            return "escalate"
        if re.search(r"\b(update|follow.?up|any news|status of (my )?ticket)\b", lower):
            return "update"
        if intent in {"ticket", "complaint", "billing", "shipping", "package_delay"}:
            return "create"
        return "create"

    async def run(self, state: AgentState) -> AgentResult:
        message = state.get("user_message") or ""
        intent = state.get("intent") or "general"
        sentiment = state.get("sentiment") or "neutral"
        action = self._detect_action(message, intent, sentiment)

        existing = re.search(r"TKT-[A-Z0-9]+", message, re.I)
        ticket_number = (
            existing.group(0).upper()
            if existing
            else f"TKT-{uuid.uuid4().hex[:8].upper()}"
        )

        pri = auto_priority(intent=intent, sentiment=sentiment, message=message)
        priority = pri["priority"]  # P1 / P2 / P3

        category = {
            "refund": "refund",
            "billing": "billing",
            "shipping": "shipping",
            "package_delay": "shipping_delay",
            "warranty": "warranty",
            "technical": "technical",
            "complaint": "complaint",
        }.get(intent, intent)

        subject = message.strip().split("\n")[0][:120] or "Support request"
        status_map = {
            "create": "open",
            "update": "in_progress",
            "close": "closed",
            "escalate": "escalated",
        }
        status = status_map[action]

        summary = await summarize_ticket(
            subject=subject,
            description=message,
            intent=intent,
            sentiment=sentiment,
        )

        ticket = {
            "ticket_number": ticket_number,
            "subject": subject,
            "description": message,
            "summary": summary.get("summary"),
            "priority": priority,
            "priority_label": pri["label"],
            "sla_minutes": pri["sla_minutes"],
            "db_priority": pri["db_priority"],
            "status": status,
            "category": category,
            "action": action,
        }

        if action in {"create", "escalate", "update"}:
            register_sla(ticket_number, priority=priority)

        messages = {
            "create": (
                f"Created support ticket **{ticket_number}** "
                f"(priority: **{priority}**, category: {category}).\n"
                f"Summary: {summary.get('summary')}"
            ),
            "update": f"Updated ticket **{ticket_number}** — status set to `{status}` ({priority}).",
            "close": f"Closed ticket **{ticket_number}**. Glad this is resolved.",
            "escalate": (
                f"Escalated ticket **{ticket_number}** to a senior specialist "
                f"(priority: **{priority}**).\nSummary: {summary.get('summary')}"
            ),
        }

        return AgentResult(
            agent_name=self.name,
            content=messages[action],
            confidence=0.88,
            data={
                "ticket_draft": ticket,
                "action": action,
                "auto_priority": pri,
                "ai_summary": summary,
                "should_create": action == "create",
                "should_update": action == "update",
                "should_close": action == "close",
                "should_escalate": action == "escalate",
            },
        )
