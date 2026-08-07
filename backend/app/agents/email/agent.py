"""Email Agent — professional replies, follow-ups, escalation emails."""

from __future__ import annotations

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent
from app.core.config import get_settings


class EmailAgent(BaseAgent):
    """Generates professional replies, follow-ups, and escalation emails."""

    name = AgentName.EMAIL

    def _template(
        self,
        *,
        kind: str,
        customer_name: str,
        intent: str,
        body_core: str,
        ticket_number: str | None,
    ) -> tuple[str, str]:
        settings = get_settings()
        brand = settings.app_name
        if kind == "escalation":
            subject = f"[{brand}] Escalation — {ticket_number or intent}"
            body = (
                f"Dear {customer_name},\n\n"
                "Thank you for your patience. Your case has been escalated to a "
                "senior support specialist who will follow up shortly"
                + (f" under ticket {ticket_number}" if ticket_number else "")
                + ".\n\n"
                f"Summary of your request:\n{body_core}\n\n"
                "We apologize for any inconvenience and appreciate your business.\n\n"
                f"Best regards,\n{brand} Support"
            )
        elif kind == "follow_up":
            subject = f"[{brand}] Follow-up on your request"
            body = (
                f"Hi {customer_name},\n\n"
                "Just checking in on your recent support request"
                + (f" ({ticket_number})" if ticket_number else "")
                + ".\n\n"
                f"{body_core}\n\n"
                "If everything looks good, no action is needed. "
                "Reply to this email if you still need help.\n\n"
                f"Warm regards,\n{brand} Support"
            )
        else:  # professional reply
            subject = f"[{brand}] Re: {intent.replace('_', ' ').title()}"
            body = (
                f"Hello {customer_name},\n\n"
                "Thanks for contacting us. Here's an update on your request:\n\n"
                f"{body_core}\n\n"
                "Please let us know if you have any other questions.\n\n"
                f"Sincerely,\n{brand} Support Team"
            )
        return subject, body

    async def run(self, state: AgentState) -> AgentResult:
        settings = get_settings()
        intent = state.get("intent") or "general"
        sentiment = state.get("sentiment") or "neutral"
        meta = state.get("metadata") or {}
        agent_results = state.get("agent_results") or {}

        ticket = (
            (agent_results.get("ticket") or {}).get("data", {}).get("ticket_draft")
            or meta.get("package_delay_ticket")
            or {}
        )
        ticket_number = ticket.get("ticket_number")

        if state.get("handoff_required") or sentiment in {"angry", "urgent"}:
            kind = "escalation"
        elif "follow" in (state.get("user_message") or "").lower():
            kind = "follow_up"
        else:
            kind = "professional_reply"

        # Prefer richest specialist content for the email body
        body_core = ""
        for key in ("package_delay", "order", "refund", "knowledge", "ticket"):
            content = (agent_results.get(key) or {}).get("content")
            if content:
                body_core = content[:800]
                break
        if not body_core:
            body_core = (state.get("user_message") or "")[:500]

        customer_name = (
            meta.get("customer_name")
            or (meta.get("email") or "Customer").split("@")[0].title()
        )
        subject, body = self._template(
            kind=kind,
            customer_name=customer_name,
            intent=intent,
            body_core=body_core,
            ticket_number=ticket_number,
        )

        payload = {
            "kind": kind,
            "to": meta.get("email") or meta.get("customer_email"),
            "subject": subject,
            "body": body,
            "ticket_number": ticket_number,
            "webhook": f"{settings.n8n_webhook_base_url}/aics-email",
            "queued": True,
        }

        return AgentResult(
            agent_name=self.name,
            content=f"Prepared {kind.replace('_', ' ')} email: {subject}",
            confidence=0.86,
            data={"email": payload, "kinds": ["professional_reply", "follow_up", "escalation"]},
        )
