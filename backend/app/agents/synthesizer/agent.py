"""Response Synthesizer — system prompt, few-shot tuning, memory-aware replies."""

from __future__ import annotations

from typing import Any

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent
from app.core.config import get_settings
from app.llm.base import LLMMessage, StubLLMAdapter, get_llm_adapter
from app.prompts.registry import get_prompt_registry


class ResponseSynthesizerAgent(BaseAgent):
    """
    Applies prompt engineering:
    - System prompt (AI Customer Support Specialist)
    - Few-shot tuning
    - Memory-aware context
    - Clarification when confidence < 90%
    - Summary + next best action
    """

    name = AgentName.SYNTHESIZER

    def _collect_specialist_context(self, state: AgentState) -> str:
        agent_results = state.get("agent_results") or {}
        parts: list[str] = []
        for name in (
            "intent",
            "sentiment",
            "knowledge",
            "graph_rag",
            "order",
            "package_delay",
            "refund",
            "ticket",
            "recommendation",
            "email",
            "handoff",
        ):
            result = agent_results.get(name) or {}
            if result.get("content"):
                parts.append(f"[{name}] {result['content']}")
        meta = state.get("metadata") or {}
        if meta.get("memory_block"):
            parts.append("[memory]\n" + str(meta["memory_block"]))
        elif meta.get("long_term_memory"):
            parts.append(
                "[customer_history] " + "; ".join(meta["long_term_memory"][-5:])
            )
        if state.get("citations"):
            cites = [
                f"{c.get('source')} ({c.get('score')})"
                for c in state["citations"][:3]
                if isinstance(c, dict)
            ]
            if cites:
                parts.append("[citations] " + "; ".join(cites))
        return "\n".join(parts)

    def _prefer_specialist_content(self, state: AgentState) -> str | None:
        agent_results = state.get("agent_results") or {}
        for key in (
            "package_delay",
            "refund",
            "order",
            "knowledge",
            "ticket",
            "recommendation",
        ):
            result = agent_results.get(key) or {}
            if result.get("success") and float(result.get("confidence") or 0) >= 0.7:
                content = result.get("content") or ""
                if content:
                    return content
        return None

    def _needs_clarification(self, confidence: float, threshold: float) -> bool:
        return confidence < threshold

    def _append_summary_and_action(
        self,
        text: str,
        *,
        intent: str,
        summary: str | None = None,
        next_action: str | None = None,
    ) -> str:
        lower = text.lower()
        out = text.rstrip()
        if "summary:" not in lower:
            out += f"\n\nSummary: {summary or f'Handled {intent} request.'}"
        if "next best action:" not in lower:
            out += f"\nNext best action: {next_action or 'Reply with any missing details or confirm to proceed.'}"
        return out

    def _clarification_reply(self, state: AgentState, confidence: float) -> str:
        intent = state.get("intent") or "your request"
        msg = state.get("user_message") or ""
        summary = (state.get("metadata") or {}).get("conversation_summary") or msg[:120]
        return (
            "I want to make sure I help you correctly — could you share a bit more detail "
            f"(for example an order ID like ORD-1001, or what you already tried)? "
            f"I currently understand this as **{intent}** (confidence {confidence:.0%}).\n\n"
            f"Summary: {summary}\n"
            "Next best action: Reply with clarifying details so I can use the right policy and tools."
        )

    def _payment_failed_playbook(self, state: AgentState) -> str | None:
        msg = (state.get("user_message") or "").lower()
        intent = state.get("intent") or ""
        if ("payment" in msg and "fail" in msg) or (
            intent in {"ticket", "billing"} and "payment" in msg
        ):
            ticket = (state.get("agent_results") or {}).get("ticket") or {}
            ticket_txt = ""
            draft = (ticket.get("data") or {}).get("ticket_draft") or {}
            if draft.get("ticket_number"):
                ticket_txt = (
                    f" I also opened billing ticket **{draft['ticket_number']}** "
                    "so we can follow up if the retry fails."
                )
            return (
                "I'm sorry your payment didn't go through. Per our Payment Policy, "
                "failed charges are not captured — please retry with the same or another card, "
                "and ensure the billing address matches your bank records."
                f"{ticket_txt}\n\n"
                "Summary: Payment failure reported; Billing intent with Payment Policy applied.\n"
                "Next best action: Retry the payment, or ask me to escalate the billing ticket."
            )
        return None

    async def run(self, state: AgentState) -> AgentResult:
        settings = get_settings()
        agent_results = state.get("agent_results") or {}
        confidence = float(state.get("confidence") or 0.0)
        clarification_threshold = float(
            getattr(settings, "clarification_confidence_threshold", 0.9) or 0.9
        )
        intent = str(state.get("intent") or "general")
        meta = state.get("metadata") or {}

        # Handoff short-circuit
        if state.get("handoff_required"):
            handoff = agent_results.get("handoff") or {}
            pkg = agent_results.get("package_delay") or {}
            if pkg.get("content") and float(pkg.get("confidence") or 0) >= 0.8:
                final = pkg["content"]
                reasons = (pkg.get("data") or {}).get("escalate_reasons") or []
                final += (
                    "\n\nA specialist is being connected now"
                    + (f" ({', '.join(reasons)})." if reasons else ".")
                )
            else:
                final = handoff.get(
                    "content",
                    "I'm connecting you with a human support specialist who can help further.",
                )
            final = self._append_summary_and_action(
                final,
                intent=intent,
                summary="Conversation escalated to a human specialist.",
                next_action="Stay on the line / watch chat for the agent handoff.",
            )
            return AgentResult(
                agent_name=self.name,
                success=True,
                content=final,
                confidence=0.95,
                data={"mode": "handoff", "llm_used": False},
            )

        # Clarification gate (confidence < 90%) unless specialists already grounded an answer
        if self._needs_clarification(confidence, clarification_threshold):
            pkg = agent_results.get("package_delay") or {}
            order = agent_results.get("order") or {}
            knowledge = agent_results.get("knowledge") or {}
            ticket = agent_results.get("ticket") or {}
            grounded = any(
                result.get("content") and float(result.get("confidence") or 0) >= 0.7
                for result in (pkg, order, knowledge, ticket)
            )
            if not grounded:
                return AgentResult(
                    agent_name=self.name,
                    success=True,
                    content=self._clarification_reply(state, confidence),
                    confidence=confidence,
                    data={
                        "mode": "clarification",
                        "llm_used": False,
                        "clarification_threshold": clarification_threshold,
                    },
                )

        pkg = agent_results.get("package_delay") or {}
        if pkg.get("content") and float(pkg.get("confidence") or 0) >= 0.8:
            return AgentResult(
                agent_name=self.name,
                success=True,
                content=self._append_summary_and_action(
                    pkg["content"],
                    intent=intent,
                    summary="Ran package-delay playbook.",
                    next_action="Confirm refund/replacement preference or wait for ticket updates.",
                ),
                confidence=float(pkg.get("confidence") or 0.9),
                data={
                    "mode": "workflow",
                    "workflow": "package_delay",
                    "llm_used": False,
                    "steps": (pkg.get("data") or {}).get("steps"),
                },
            )

        playbook = self._payment_failed_playbook(state)
        if playbook:
            return AgentResult(
                agent_name=self.name,
                success=True,
                content=playbook,
                confidence=max(confidence, 0.9),
                data={
                    "mode": "few_shot_playbook",
                    "playbook": "payment_failed",
                    "llm_used": False,
                },
            )

        context_block = self._collect_specialist_context(state)
        specialist = self._prefer_specialist_content(state)
        memory_block = str(meta.get("memory_block") or "")

        registry = get_prompt_registry()
        system, variant, tmpl = registry.render_master_system(
            session_id=state.get("session_id") or "anon",
            app_name=settings.app_name,
            intent=intent,
            sentiment=str(state.get("sentiment") or "neutral"),
            confidence=confidence,
            handoff_threshold=settings.handoff_confidence_threshold,
            clarification_threshold=clarification_threshold,
            context_block=context_block,
            memory_block=memory_block,
        )

        llm = get_llm_adapter()
        response = await llm.complete(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(
                    role="user",
                    content=(
                        f"Customer message: {state.get('user_message') or ''}\n\n"
                        f"Specialist findings:\n{context_block or '(none)'}\n\n"
                        "Respond politely using retrieved knowledge only. "
                        "Never hallucinate. Include Summary and Next best action."
                    ),
                ),
            ]
        )
        final = response.content
        llm_used = True

        if specialist and (
            isinstance(llm, StubLLMAdapter)
            or "AI agents are initializing" in final
            or (response.model or "").startswith("stub")
        ):
            final = specialist
            recs = state.get("recommendations") or []
            if recs:
                final += "\n\nAlso consider: " + ", ".join(recs)
            llm_used = False

        final = self._append_summary_and_action(
            final or "I'm here to help.",
            intent=intent,
            summary=meta.get("conversation_summary"),
            next_action="Tell me if you want a ticket, refund, or more policy detail.",
        )

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=final,
            confidence=confidence or 0.7,
            data={
                "mode": "synthesize",
                "llm_used": llm_used,
                "prompt_variant": variant,
                "always_rules": (tmpl.always_rules if tmpl else None),
                "provider": getattr(response, "provider", None),
                "model": getattr(response, "model", None),
            },
        )
