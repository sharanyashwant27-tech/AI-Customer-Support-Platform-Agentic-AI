"""Refund processing agent — validates eligibility, fraud checks, drafts refunds."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.advanced.features import detect_refund_fraud, publish_realtime
from app.agents.order.agent import _load_orders
from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent


class RefundAgent(BaseAgent):
    name = AgentName.REFUND

    async def run(self, state: AgentState) -> AgentResult:
        message = state.get("user_message") or ""
        match = re.search(r"ORD-\d+", message, re.I)
        orders = _load_orders()
        order = None
        if match:
            oid = match.group(0).upper()
            order = next((o for o in orders if o["order_id"] == oid), None)
        if order is None and orders:
            order = orders[0]

        if not order:
            return AgentResult(
                agent_name=self.name,
                content=(
                    "I can start a refund once I have a valid order ID "
                    "(for example ORD-1001)."
                ),
                confidence=0.55,
                data={"eligible": False, "reason": "order_not_found"},
            )

        placed = datetime.fromisoformat(order["placed_at"].replace("Z", "+00:00"))
        age_days = (datetime.now(UTC) - placed).days
        status = order.get("status", "")
        within_window = age_days <= 30
        refundable_status = status in {"delivered", "shipped", "processing"}

        prior_refunds = int((state.get("metadata") or {}).get("prior_refunds") or 0)
        fraud = detect_refund_fraud(
            message=message,
            order_age_days=age_days,
            prior_refunds=prior_refunds,
        )

        eligible = within_window and refundable_status and not fraud["recommend_manual_review"]
        if fraud["risk"] == "high":
            eligible = False

        if eligible:
            refund_id = f"REF-{order['order_id'][-4:]}-{int(datetime.now(UTC).timestamp()) % 100000}"
            content = (
                f"Refund approved in principle for {order['order_id']} "
                f"(${order['total']} {order.get('currency', 'USD')}). "
                f"Reference {refund_id}. Funds typically return in 5–10 business days "
                "after inspection. I can also open a ticket to track this."
            )
            data = {
                "eligible": True,
                "refund_id": refund_id,
                "order_id": order["order_id"],
                "amount": order["total"],
                "currency": order.get("currency", "USD"),
                "age_days": age_days,
                "status": "pending_processing",
                "fraud": fraud,
            }
            confidence = 0.9
        elif fraud["recommend_manual_review"]:
            content = (
                f"Refund for {order['order_id']} needs manual review "
                f"(fraud risk: {fraud['risk']}, score {fraud['fraud_score']}). "
                "I'll escalate to a specialist before issuing funds."
            )
            data = {
                "eligible": False,
                "order_id": order["order_id"],
                "age_days": age_days,
                "reasons": ["fraud_review"] + list(fraud.get("signals") or []),
                "fraud": fraud,
                "requires_manual_review": True,
            }
            confidence = 0.85
            publish_realtime(
                "refund.fraud_flagged",
                {"order_id": order["order_id"], "fraud": fraud},
            )
        else:
            reasons = []
            if not within_window:
                reasons.append(f"outside 30-day window ({age_days} days since purchase)")
            if not refundable_status:
                reasons.append(f"order status '{status}' is not refundable")
            content = (
                f"Order {order['order_id']} is not auto-eligible for refund: "
                + "; ".join(reasons)
                + ". I can escalate to a specialist or create a ticket."
            )
            data = {
                "eligible": False,
                "order_id": order["order_id"],
                "age_days": age_days,
                "reasons": reasons,
                "fraud": fraud,
            }
            confidence = 0.8

        return AgentResult(
            agent_name=self.name,
            content=content,
            confidence=confidence,
            data=data,
        )
