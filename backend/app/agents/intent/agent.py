"""Intent Classification Agent — Refund, Complaint, Shipping, Product, Technical, Billing, Warranty."""

from __future__ import annotations

import re

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent

# Ordered by specificity (first strong match wins when scores tie via priority boost)
INTENT_PATTERNS: list[tuple[str, list[str], float]] = [
    (
        "shipping",
        [
            r"hasn.?t arrived",
            r"not arrived",
            r"package",
            r"shipment",
            r"tracking",
            r"delivery",
            r"delayed",
            r"where.?is.?my",
            r"shipping",
        ],
        0.15,
    ),
    (
        "refund",
        [r"refund", r"money.?back", r"reembolso", r"remboursement", r"charge.?back"],
        0.2,
    ),
    (
        "warranty",
        [r"warranty", r"guarantee", r"defective under warranty", r"covered"],
        0.2,
    ),
    (
        "billing",
        [
            r"billing",
            r"invoice",
            r"charged",
            r"payment",
            r"credit.?card",
            r"subscription.?fee",
            r"double.?charged",
        ],
        0.2,
    ),
    (
        "technical",
        [
            r"not.?working",
            r"broken",
            r"error",
            r"bug",
            r"crash",
            r"install",
            r"setup",
            r"troubleshoot",
            r"technical",
        ],
        0.15,
    ),
    (
        "complaint",
        [
            r"complaint",
            r"unacceptable",
            r"terrible.?service",
            r"disappointed",
            r"angry",
            r"file.?a.?complaint",
        ],
        0.15,
    ),
    (
        "product",
        [
            r"product",
            r"specs?",
            r"features?",
            r"compatible",
            r"which.?model",
            r"recommend",
            r"difference between",
        ],
        0.1,
    ),
    (
        "escalation",
        [r"human", r"speak.?to", r"representative", r"manager", r"real.?person"],
        0.25,
    ),
]


class IntentClassificationAgent(BaseAgent):
    """Classifies: Refund, Complaint, Shipping, Product, Technical, Billing, Warranty."""

    name = AgentName.INTENT

    async def run(self, state: AgentState) -> AgentResult:
        message = (state.get("user_message") or "").lower()

        from app.agents.workflows.package_delay import is_package_delay_message

        # Shipping delay playbook is a specialized shipping subtype
        if is_package_delay_message(message):
            return AgentResult(
                agent_name=self.name,
                success=True,
                content="package_delay",
                confidence=0.93,
                data={
                    "intent": "package_delay",
                    "primary_label": "shipping",
                    "subtype": "package_delay",
                    "confidence": 0.93,
                    "labels": [
                        "refund",
                        "complaint",
                        "shipping",
                        "product",
                        "technical",
                        "billing",
                        "warranty",
                    ],
                },
            )

        best_intent = "product"
        best_score = 0.35
        scores: dict[str, float] = {}

        for intent, patterns, boost in INTENT_PATTERNS:
            hits = sum(1 for p in patterns if re.search(p, message, re.IGNORECASE))
            if hits:
                score = min(0.95, 0.4 + hits * 0.18 + boost)
                scores[intent] = score
                if score > best_score:
                    best_intent = intent
                    best_score = score

        # Map taxonomy labels → master-graph specialist routes
        graph_intent = {
            "shipping": "order_status",
            "refund": "refund",
            "complaint": "ticket",
            "product": "knowledge",
            "technical": "knowledge",
            "billing": "ticket",
            "warranty": "knowledge",
            "escalation": "escalation",
        }.get(best_intent, best_intent)

        if best_intent == "shipping" and is_package_delay_message(message):
            graph_intent = "package_delay"
        elif best_intent == "product" and any(
            w in message for w in ("coupon", "discount", "upgrade", "offer", "recommend")
        ):
            graph_intent = "recommendation"
        elif "email" in message and any(
            w in message for w in ("send", "draft", "write", "follow")
        ):
            graph_intent = "email"

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=graph_intent,
            confidence=best_score,
            data={
                "intent": graph_intent,
                "primary_label": best_intent,
                "confidence": best_score,
                "scores": scores,
                "labels": [
                    "refund",
                    "complaint",
                    "shipping",
                    "product",
                    "technical",
                    "billing",
                    "warranty",
                ],
            },
        )
