"""Human Handoff Agent — transfers chat with conversation, summary, suggested resolution."""

from __future__ import annotations

from typing import Any

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent
from app.core.config import get_settings


class HumanHandoffAgent(BaseAgent):
    """
    Transfers chat to a human, including:
    - entire conversation
    - summary
    - suggested resolution
    """

    name = AgentName.HANDOFF

    def _build_summary(self, state: AgentState) -> str:
        intent = state.get("intent") or "general"
        sentiment = state.get("sentiment") or "neutral"
        msg = (state.get("user_message") or "")[:240]
        return (
            f"Customer intent appears to be '{intent}' with sentiment '{sentiment}'. "
            f"Latest message: \"{msg}\""
        )

    def _suggested_resolution(self, state: AgentState) -> str:
        agent_results = state.get("agent_results") or {}
        intent = state.get("intent") or ""
        for key in ("package_delay", "refund", "order", "ticket", "knowledge"):
            content = (agent_results.get(key) or {}).get("content")
            if content:
                return content[:500]
        if intent in {"shipping", "package_delay", "order_status"}:
            return "Verify tracking, explain delay, offer refund/replacement, open ticket."
        if intent == "refund":
            return "Confirm eligibility within 30 days and process refund to original payment method."
        if intent in {"billing", "ticket", "complaint"}:
            return "Open high-priority ticket and confirm next update window within 24 hours."
        return "Gather order/account details, answer from knowledge base, escalate if unresolved."

    def _conversation_transcript(self, state: AgentState) -> list[dict[str, Any]]:
        meta = state.get("metadata") or {}
        history = list(meta.get("conversation_history") or [])
        history.append({"role": "user", "content": state.get("user_message") or ""})
        # Include specialist notes as system context for the human agent
        notes = []
        for key, result in (state.get("agent_results") or {}).items():
            if isinstance(result, dict) and result.get("content"):
                notes.append(
                    {
                        "role": "system",
                        "content": f"[{key}] {str(result['content'])[:300]}",
                    }
                )
        return history + notes[:6]

    async def run(self, state: AgentState) -> AgentResult:
        settings = get_settings()
        confidence = float(state.get("confidence") or 0.0)
        intent = state.get("intent") or "general"
        sentiment = state.get("sentiment") or "neutral"
        message = (state.get("user_message") or "").lower()
        meta = state.get("metadata") or {}
        pkg = (state.get("agent_results") or {}).get("package_delay") or {}
        pkg_data = pkg.get("data") or {}

        reasons: list[str] = []
        if intent == "escalation":
            reasons.append("customer_requested_human")
        if confidence < settings.handoff_confidence_threshold:
            reasons.append("low_confidence")
        if sentiment in {"angry", "frustrated", "urgent", "negative"}:
            reasons.append(f"sentiment_{sentiment}")
        if any(w in message for w in ("lawsuit", "attorney", "legal", "lawyer")):
            reasons.append("legal_risk")
        if meta.get("force_handoff") or pkg_data.get("escalate"):
            reasons.append("workflow_escalation")
            reasons.extend(pkg_data.get("escalate_reasons") or [])

        # de-dupe reasons
        reasons = list(dict.fromkeys(reasons))
        handoff = bool(reasons)

        summary = self._build_summary(state)
        suggested = self._suggested_resolution(state)
        transcript = self._conversation_transcript(state)

        payload = {
            "handoff_required": handoff,
            "reasons": reasons,
            "conversation": transcript,
            "summary": summary,
            "suggested_resolution": suggested,
            "session_id": state.get("session_id"),
            "customer_id": state.get("customer_id"),
            "intent": intent,
            "sentiment": sentiment,
        }

        if handoff:
            content = (
                "Connecting you with a human support specialist.\n\n"
                f"**Summary for agent:** {summary}\n\n"
                f"**Suggested resolution:** {suggested}"
            )
        else:
            content = "No handoff required."

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=content,
            confidence=1.0 if handoff else 0.9,
            data=payload,
        )
