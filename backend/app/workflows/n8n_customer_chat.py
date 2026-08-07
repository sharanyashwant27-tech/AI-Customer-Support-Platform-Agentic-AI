"""n8n Customer Chat workflow steps.

Customer Chat → Webhook → Intent Detection → Knowledge Search → Vector Search
→ LLM → CRM Update → Ticket Creation → Email → Slack Notification → Customer Response
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.agents.intent.agent import IntentClassificationAgent
from app.agents.sentiment.agent import SentimentAnalysisAgent
from app.agents.ticket.agent import TicketManagementAgent
from app.channels.base import Channel, ChannelReply
from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.hub import integration_hub
from app.llm.base import LLMMessage, StubLLMAdapter, get_llm_adapter
from app.memory.conversation import ensure_memory
from app.prompts.registry import get_prompt_registry
from app.rag.pipeline import rag_pipeline
from app.workflows.events import event_publisher

logger = get_logger(__name__)

WORKFLOW_STEPS = [
    "customer_chat",
    "webhook",
    "intent_detection",
    "knowledge_search",
    "vector_search",
    "llm",
    "crm_update",
    "ticket_creation",
    "email",
    "slack_notification",
    "customer_response",
]


class N8nCustomerChatWorkflow:
    """Backend steps called by the n8n Customer Chat workflow."""

    async def intent_detection(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message") or payload.get("user_message") or "")
        state = {
            "user_message": message,
            "session_id": payload.get("session_id") or f"n8n-{uuid4().hex[:8]}",
            "customer_id": payload.get("customer_id"),
        }
        intent = await IntentClassificationAgent().run(state)
        sentiment = await SentimentAnalysisAgent().run(state)
        return {
            **payload,
            "session_id": state["session_id"],
            "message": message,
            "intent": (intent.data or {}).get("intent", "general"),
            "primary_label": (intent.data or {}).get("primary_label"),
            "confidence": float((intent.data or {}).get("confidence") or intent.confidence),
            "sentiment": (sentiment.data or {}).get("sentiment", "neutral"),
            "step": "intent_detection",
            "workflow_path": ["customer_chat", "webhook", "intent_detection"],
        }

    async def knowledge_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Knowledge Search (RAG answer path / source-aware retrieve)."""
        query = str(payload.get("message") or "")
        answer = await rag_pipeline.answer(query, language=str(payload.get("language") or "en"))
        return {
            **payload,
            "knowledge_answer": answer.get("answer"),
            "knowledge_citations": answer.get("citations") or [],
            "knowledge_llm_used": answer.get("llm_used"),
            "step": "knowledge_search",
            "workflow_path": list(payload.get("workflow_path") or []) + ["knowledge_search"],
        }

    async def vector_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Vector Search stage (explicit retriever)."""
        query = str(payload.get("message") or "")
        citations = await rag_pipeline.retrieve(query, top_k=int(payload.get("top_k") or 5))
        return {
            **payload,
            "vector_citations": citations,
            "vector_hit_count": len(citations),
            "step": "vector_search",
            "workflow_path": list(payload.get("workflow_path") or []) + ["vector_search"],
        }

    async def llm(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        registry = get_prompt_registry()
        system, variant, _tmpl = registry.render_master_system(
            session_id=str(payload.get("session_id") or "n8n"),
            app_name=settings.app_name,
            intent=str(payload.get("intent") or "general"),
            sentiment=str(payload.get("sentiment") or "neutral"),
            confidence=float(payload.get("confidence") or 0.0),
            handoff_threshold=settings.handoff_confidence_threshold,
            clarification_threshold=settings.clarification_confidence_threshold,
            context_block=self._context_block(payload),
            memory_block=str(payload.get("memory_block") or ""),
        )
        llm = get_llm_adapter()
        response = await llm.complete(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(
                    role="user",
                    content=(
                        f"Customer message: {payload.get('message')}\n\n"
                        f"Intent: {payload.get('intent')}\n"
                        f"Knowledge: {payload.get('knowledge_answer') or '(none)'}\n"
                        "Respond politely. Never hallucinate. Include Summary and Next best action."
                    ),
                ),
            ]
        )
        text = response.content
        llm_used = not isinstance(llm, StubLLMAdapter)
        if not llm_used or "AI agents are initializing" in text:
            # Prefer grounded knowledge / vector excerpts offline
            text = payload.get("knowledge_answer") or self._fallback_from_vectors(payload)
            llm_used = False
        if "Summary:" not in text:
            text += f"\n\nSummary: Handled {payload.get('intent')} via n8n Customer Chat workflow."
        if "Next best action:" not in text:
            text += "\nNext best action: Reply if you need a ticket update or more help."

        return {
            **payload,
            "llm_response": text,
            "llm_used": llm_used,
            "prompt_variant": variant,
            "step": "llm",
            "workflow_path": list(payload.get("workflow_path") or []) + ["llm"],
        }

    async def crm_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """CRM Update — sync profile / last interaction into customer memory."""
        memory = await ensure_memory()
        customer_id = payload.get("customer_id") or payload.get("email") or "anonymous"
        session_id = str(payload.get("session_id") or "")
        profile = await memory.update_profile(
            str(customer_id),
            {
                "customer_id": str(customer_id),
                "email": payload.get("email"),
                "last_intent": payload.get("intent"),
                "last_sentiment": payload.get("sentiment"),
                "last_session_id": session_id,
                "last_channel": payload.get("channel") or "web",
                "crm_synced": True,
            },
        )
        if payload.get("preferences"):
            await memory.set_preferences(str(customer_id), dict(payload["preferences"]))
        await memory.remember_long_term(
            str(customer_id),
            f"n8n chat intent={payload.get('intent')} session={session_id}",
        )
        await event_publisher.publish(
            "crm.updated",
            {
                "customer_id": customer_id,
                "intent": payload.get("intent"),
                "session_id": session_id,
            },
        )
        return {
            **payload,
            "customer_id": customer_id,
            "crm_profile": profile,
            "crm_updated": True,
            "step": "crm_update",
            "workflow_path": list(payload.get("workflow_path") or []) + ["crm_update"],
        }

    async def ticket_creation(self, payload: dict[str, Any]) -> dict[str, Any]:
        intent = str(payload.get("intent") or "")
        sentiment = str(payload.get("sentiment") or "neutral")
        message = str(payload.get("message") or "")
        should_create = payload.get("force_ticket") or intent in {
            "ticket",
            "billing",
            "complaint",
            "escalation",
            "package_delay",
            "refund",
        } or sentiment in {"angry", "urgent", "frustrated"}

        ticket_draft = None
        if should_create:
            result = await TicketManagementAgent().run(
                {
                    "user_message": message,
                    "intent": intent or "ticket",
                    "sentiment": sentiment,
                }
            )
            ticket_draft = (result.data or {}).get("ticket_draft")
            if ticket_draft and payload.get("customer_id"):
                memory = await ensure_memory()
                await memory.remember_ticket(str(payload["customer_id"]), ticket_draft)
            await event_publisher.publish("ticket.created", ticket_draft or {})

        return {
            **payload,
            "ticket_created": bool(ticket_draft),
            "ticket": ticket_draft,
            "step": "ticket_creation",
            "workflow_path": list(payload.get("workflow_path") or []) + ["ticket_creation"],
        }

    async def email_notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        to_email = payload.get("email") or payload.get("customer_email")
        body = str(payload.get("llm_response") or payload.get("knowledge_answer") or "")
        reply = ChannelReply(
            text=body,
            channel=Channel.EMAIL,
            session_id=str(payload.get("session_id") or ""),
            language=str(payload.get("language") or "en"),
            intent=payload.get("intent"),
            sentiment=payload.get("sentiment"),
            metadata={"ticket": payload.get("ticket")},
        )
        result = {"status": "skipped", "reason": "no_email"}
        if to_email:
            subject = None
            ticket = payload.get("ticket") or {}
            if ticket.get("ticket_number"):
                subject = f"[{settings.app_name}] Ticket {ticket['ticket_number']}"
            result = await integration_hub.send_email(
                reply, to_email=str(to_email), subject=subject
            )
        return {
            **payload,
            "email_result": result,
            "step": "email",
            "workflow_path": list(payload.get("workflow_path") or []) + ["email"],
        }

    async def slack_notification(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = str(payload.get("llm_response") or "")
        ticket = payload.get("ticket") or {}
        text = (
            f"*n8n Customer Chat*\n"
            f"Intent: `{payload.get('intent')}` · Sentiment: `{payload.get('sentiment')}`\n"
            f"Session: `{payload.get('session_id')}`\n"
        )
        if ticket.get("ticket_number"):
            text += f"Ticket: `{ticket['ticket_number']}`\n"
        text += f"\n{body[:500]}"
        reply = ChannelReply(
            text=text,
            channel=Channel.SLACK,
            session_id=str(payload.get("session_id") or ""),
            language=str(payload.get("language") or "en"),
            intent=payload.get("intent"),
            sentiment=payload.get("sentiment"),
        )
        result = await integration_hub.notify_slack(reply)
        return {
            **payload,
            "slack_result": result,
            "step": "slack_notification",
            "workflow_path": list(payload.get("workflow_path") or [])
            + ["slack_notification"],
        }

    async def customer_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Final Customer Response payload (returned by n8n webhook)."""
        memory = await ensure_memory()
        session_id = str(payload.get("session_id") or "")
        response_text = str(
            payload.get("llm_response")
            or payload.get("knowledge_answer")
            or "Thanks for contacting support — we're looking into this."
        )
        await memory.add_turn(
            session_id,
            role="assistant",
            content=response_text,
            metadata={
                "workflow": "n8n_customer_chat",
                "intent": payload.get("intent"),
                "ticket": (payload.get("ticket") or {}).get("ticket_number"),
            },
        )
        await event_publisher.publish(
            "chat.message",
            {
                "session_id": session_id,
                "intent": payload.get("intent"),
                "response_preview": response_text[:200],
            },
        )
        path = list(payload.get("workflow_path") or []) + ["customer_response"]
        return {
            "ok": True,
            "workflow": "n8n_customer_chat",
            "steps": WORKFLOW_STEPS,
            "workflow_path": path,
            "session_id": session_id,
            "customer_id": payload.get("customer_id"),
            "intent": payload.get("intent"),
            "sentiment": payload.get("sentiment"),
            "confidence": payload.get("confidence"),
            "ticket": payload.get("ticket"),
            "crm_updated": payload.get("crm_updated"),
            "email_result": payload.get("email_result"),
            "slack_result": payload.get("slack_result"),
            "response": response_text,
            "citations": payload.get("vector_citations")
            or payload.get("knowledge_citations")
            or [],
        }

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the full n8n Customer Chat pipeline in-process (for tests / fallback)."""
        data = await self.intent_detection(payload)
        data = await self.knowledge_search(data)
        data = await self.vector_search(data)
        data = await self.llm(data)
        data = await self.crm_update(data)
        data = await self.ticket_creation(data)
        data = await self.email_notify(data)
        data = await self.slack_notification(data)
        return await self.customer_response(data)

    def _context_block(self, payload: dict[str, Any]) -> str:
        parts = []
        if payload.get("knowledge_answer"):
            parts.append(f"[knowledge] {payload['knowledge_answer']}")
        cites = payload.get("vector_citations") or []
        if cites:
            parts.append(
                "[vector] "
                + "; ".join(
                    f"{c.get('source')}: {(c.get('excerpt') or '')[:120]}"
                    for c in cites[:3]
                )
            )
        return "\n".join(parts)

    def _fallback_from_vectors(self, payload: dict[str, Any]) -> str:
        cites = payload.get("vector_citations") or payload.get("knowledge_citations") or []
        if not cites:
            return (
                "Thanks for reaching out. I couldn't find a matching article yet — "
                "could you share your order ID or a bit more detail?"
            )
        bullets = "\n".join(f"- {c.get('excerpt')}" for c in cites[:3] if c.get("excerpt"))
        return f"Based on our knowledge base:\n{bullets}"


n8n_customer_chat = N8nCustomerChatWorkflow()
