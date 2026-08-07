"""Amazon-style package delay resolution — order → shipment → delay → refund → ticket → escalate."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.order.agent import _load_orders
from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent
from app.core.logging import get_logger

logger = get_logger(__name__)

PACKAGE_DELAY_CUES = re.compile(
    r"(hasn.?t arrived|have not arrived|not arrived|still waiting|delayed|"
    r"late delivery|missing package|where.?s my package|package.*(late|missing|lost)|"
    r"no.?show|never (got|received)|didn.?t (get|receive))",
    re.I,
)


def is_package_delay_message(text: str) -> bool:
    return bool(PACKAGE_DELAY_CUES.search(text or ""))


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _find_order(message: str, orders: list[dict[str, Any]]) -> dict[str, Any] | None:
    match = re.search(r"ORD-\d+", message, re.I)
    if match:
        oid = match.group(0).upper()
        found = next((o for o in orders if o["order_id"] == oid), None)
        if found:
            return found
    # Prefer a delayed shipped order when customer doesn't specify
    now = datetime.now(UTC)
    delayed = []
    for order in orders:
        eta = _parse_dt(order.get("estimated_delivery"))
        if order.get("status") in {"shipped", "out_for_delivery", "processing"} and eta and eta < now:
            delayed.append(order)
    if delayed:
        return delayed[0]
    return orders[0] if orders else None


class PackageDelayWorkflow(BaseAgent):
    """
    End-to-end delayed-package playbook:

    1. Check order
    2. Check shipment / tracking
    3. Measure delay
    4. Explain delay
    5. Offer refund / replacement
    6. Create support ticket
    7. Escalate when thresholds are breached
    """

    name = AgentName.ORDER  # surfaced under order family; workflow tag in data

    async def run(self, state: AgentState) -> AgentResult:
        message = state.get("user_message") or ""
        sentiment = (state.get("sentiment") or "neutral").lower()
        orders = _load_orders()
        steps: list[dict[str, Any]] = []

        # 1) Check order
        order = _find_order(message, orders)
        if not order:
            steps.append({"step": "check_order", "status": "failed"})
            return AgentResult(
                agent_name=self.name,
                content=(
                    "I couldn't find an order on your account. "
                    "Please share an order ID like ORD-1001 so I can investigate the shipment."
                ),
                confidence=0.5,
                data={"workflow": "package_delay", "steps": steps, "escalate": False},
            )

        steps.append(
            {
                "step": "check_order",
                "status": "ok",
                "order_id": order["order_id"],
                "order_status": order.get("status"),
                "total": order.get("total"),
            }
        )

        # 2) Check shipment
        tracking = order.get("tracking_number")
        shipment = order.get("shipment") or {}
        carrier = shipment.get("carrier") or "UPS"
        last_scan = shipment.get("last_scan") or (
            "In transit — departing regional hub"
            if tracking
            else "Label created — awaiting carrier pickup"
        )
        shipment_status = shipment.get("status") or order.get("status")
        steps.append(
            {
                "step": "check_shipment",
                "status": "ok",
                "tracking_number": tracking,
                "carrier": carrier,
                "shipment_status": shipment_status,
                "last_scan": last_scan,
            }
        )

        # 3) Check delay
        now = datetime.now(UTC)
        eta = _parse_dt(order.get("estimated_delivery"))
        delay_days = 0
        if eta:
            delay_days = max(0, (now.date() - eta.date()).days)
        is_delayed = delay_days > 0 and order.get("status") not in {"delivered", "refunded", "cancelled"}
        severity = "none"
        if delay_days >= 5:
            severity = "critical"
        elif delay_days >= 2:
            severity = "high"
        elif delay_days >= 1:
            severity = "medium"
        elif order.get("status") == "shipped":
            severity = "watch"

        steps.append(
            {
                "step": "check_delay",
                "status": "ok",
                "estimated_delivery": order.get("estimated_delivery"),
                "delay_days": delay_days,
                "is_delayed": is_delayed,
                "severity": severity,
            }
        )

        # 4) Explain delay
        if is_delayed:
            explanation = (
                f"Your order {order['order_id']} was estimated for delivery on "
                f"{eta.date().isoformat() if eta else 'the promised date'}, and it is now "
                f"{delay_days} day(s) late. Carrier {carrier} last reported: “{last_scan}”. "
                "Delays like this are usually caused by regional sorting congestion or a missed scan."
            )
        elif order.get("status") == "processing":
            explanation = (
                f"Order {order['order_id']} is still being prepared and does not have a tracking "
                "number yet. It has not entered the carrier network."
            )
        else:
            explanation = (
                f"Order {order['order_id']} is marked **{order.get('status')}** with tracking "
                f"{tracking or 'pending'}. It does not appear past the delivery window yet."
            )
        steps.append({"step": "explain_delay", "status": "ok", "explanation": explanation})

        # 5) Offer refund / replacement when delayed
        offer_refund = is_delayed and delay_days >= 1
        offer_replacement = is_delayed and delay_days >= 3
        refund_id = None
        if offer_refund:
            refund_id = f"REF-{order['order_id'][-4:]}-{uuid.uuid4().hex[:5].upper()}"
            offer_text = (
                f"I can start a full refund of ${order.get('total')} "
                f"{order.get('currency', 'USD')} (ref {refund_id})"
            )
            if offer_replacement:
                offer_text += " or ship a replacement at no charge"
            offer_text += ". Reply with “refund” or “replacement” and I’ll process it."
        else:
            offer_text = (
                "I’m monitoring this shipment closely. If it isn’t delivered within 24 hours, "
                "I can automatically issue a refund or replacement."
            )
        steps.append(
            {
                "step": "offer_refund",
                "status": "ok",
                "offer_refund": offer_refund,
                "offer_replacement": offer_replacement,
                "refund_id": refund_id,
                "offer_text": offer_text,
            }
        )

        # 6) Create support ticket
        ticket_number = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        ticket = {
            "ticket_number": ticket_number,
            "subject": f"Delayed package — {order['order_id']}",
            "description": message,
            "priority": "urgent" if severity in {"high", "critical"} else "high",
            "category": "shipping_delay",
            "status": "open",
            "order_id": order["order_id"],
        }
        steps.append({"step": "create_ticket", "status": "ok", "ticket": ticket})

        # 7) Escalate if needed
        escalate = False
        escalate_reasons: list[str] = []
        if severity in {"high", "critical"}:
            escalate = True
            escalate_reasons.append(f"delay_severity_{severity}")
        if sentiment in {"negative", "angry", "frustrated", "urgent"}:
            escalate = True
            escalate_reasons.append(f"sentiment_{sentiment}")
        if delay_days >= 5:
            escalate = True
            escalate_reasons.append("delay_over_5_days")
        if any(w in message.lower() for w in ("lawsuit", "attorney", "manager", "unacceptable")):
            escalate = True
            escalate_reasons.append("customer_escalation_language")

        steps.append(
            {
                "step": "escalate_if_needed",
                "status": "ok",
                "escalate": escalate,
                "reasons": escalate_reasons,
            }
        )

        # Compose customer-facing narrative
        lines = [
            "I’ve looked into this end-to-end:",
            "",
            f"**1. Order** — {order['order_id']} · status `{order.get('status')}` · "
            f"${order.get('total')} {order.get('currency', 'USD')}",
            f"**2. Shipment** — {carrier} · tracking `{tracking or 'not assigned yet'}` · {last_scan}",
            f"**3. Delay** — "
            + (
                f"{delay_days} day(s) past estimated delivery ({eta.date().isoformat() if eta else 'n/a'})"
                if is_delayed
                else "not past the delivery window yet"
            ),
            f"**4. What’s going on** — {explanation}",
            f"**5. Resolution options** — {offer_text}",
            f"**6. Support ticket** — I opened **{ticket_number}** so this stays tracked.",
        ]
        if escalate:
            lines.append(
                "**7. Escalation** — I’m connecting you with a specialist because: "
                + ", ".join(escalate_reasons)
                + "."
            )
        else:
            lines.append(
                "**7. Escalation** — Not required yet; I’ll keep monitoring and escalate "
                "automatically if the delay grows or you ask for a human."
            )

        content = "\n".join(lines)
        logger.info(
            "package_delay_workflow",
            order_id=order["order_id"],
            delay_days=delay_days,
            escalate=escalate,
            ticket=ticket_number,
        )

        # Async fan-out to RabbitMQ → n8n / workers
        try:
            from app.workflows.events import event_publisher

            await event_publisher.publish(
                "package.delayed",
                {
                    "order_id": order["order_id"],
                    "delay_days": delay_days,
                    "ticket": ticket,
                    "escalate": escalate,
                    "refund_id": refund_id,
                },
            )
            if offer_refund:
                await event_publisher.publish(
                    "refund.offered",
                    {"order_id": order["order_id"], "refund_id": refund_id},
                )
            await event_publisher.publish("ticket.created", ticket)
            if escalate:
                await event_publisher.publish(
                    "handoff.requested",
                    {
                        "order_id": order["order_id"],
                        "reasons": escalate_reasons,
                        "ticket_number": ticket_number,
                    },
                )
        except Exception as exc:
            logger.warning("package_delay_events_failed", error=str(exc))

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=content,
            confidence=0.93,
            data={
                "workflow": "package_delay",
                "steps": steps,
                "order": order,
                "ticket": ticket,
                "offer_refund": offer_refund,
                "refund_id": refund_id,
                "escalate": escalate,
                "escalate_reasons": escalate_reasons,
                "delay_days": delay_days,
                "severity": severity,
            },
        )
