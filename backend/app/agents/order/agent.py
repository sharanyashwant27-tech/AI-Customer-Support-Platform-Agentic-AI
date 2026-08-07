"""Order Management Agent — status: Delivered, Delayed, Returned, Cancelled (+ shipped/processing)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent

_SAMPLE_CANDIDATES = [
    Path(__file__).resolve().parents[4] / "sample_data" / "orders" / "sample_orders.json",
    Path("/sample_data/orders/sample_orders.json"),
]

STATUS_LABELS = {
    "delivered": "Delivered",
    "delayed": "Delayed",
    "returned": "Returned",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
    "shipped": "Shipped",
    "processing": "Processing",
    "out_for_delivery": "Out for delivery",
}


def _load_orders() -> list[dict]:
    for path in _SAMPLE_CANDIDATES:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


def _normalize_status(order: dict) -> str:
    raw = (order.get("status") or "").lower()
    if raw in {"delivered", "returned", "cancelled", "canceled", "processing", "shipped"}:
        if raw == "canceled":
            return "cancelled"
        # Treat past-ETA shipped orders as delayed
        if raw == "shipped":
            eta = order.get("estimated_delivery")
            if eta:
                try:
                    eta_dt = datetime.fromisoformat(eta.replace("Z", "+00:00"))
                    if eta_dt.date() < datetime.now(UTC).date():
                        return "delayed"
                except Exception:
                    pass
        return raw
    return raw or "processing"


class OrderManagementAgent(BaseAgent):
    """Checks order status and returns Delivered / Delayed / Returned / Cancelled."""

    name = AgentName.ORDER

    async def run(self, state: AgentState) -> AgentResult:
        message = state.get("user_message") or ""
        match = re.search(r"ORD-\d+", message, re.I)
        orders = _load_orders()
        order = None
        if match:
            oid = match.group(0).upper()
            order = next((o for o in orders if o["order_id"] == oid), None)
        if order is None and orders:
            if re.search(r"order|track|shipment|delivery|package|shipping", message, re.I):
                order = orders[0]

        if not order:
            return AgentResult(
                agent_name=self.name,
                content="I couldn't find that order. Please provide an order ID like ORD-1001.",
                confidence=0.4,
                data={"found": False, "statuses": list(STATUS_LABELS.values())},
            )

        status_key = _normalize_status(order)
        status_label = STATUS_LABELS.get(status_key, status_key.title())
        shipment = order.get("shipment") or {}

        lines = [
            f"**Order** {order['order_id']} — status **{status_label}**",
            f"Total: ${order['total']} {order.get('currency', 'USD')}",
        ]
        if order.get("tracking_number"):
            lines.append(f"Tracking: `{order['tracking_number']}`")
        if order.get("estimated_delivery"):
            lines.append(f"Estimated delivery: {order['estimated_delivery']}")
        if shipment.get("last_scan"):
            lines.append(f"Last scan: {shipment['last_scan']}")

        if status_key == "delayed":
            lines.append(
                "This shipment is past its estimated delivery window. "
                "I can offer a refund, replacement, or open a ticket."
            )
        elif status_key == "delivered":
            lines.append("Marked delivered. If you didn't receive it, I can open a missing-package ticket.")
        elif status_key == "returned":
            lines.append("Return received. Refund timing is typically 5–10 business days after inspection.")
        elif status_key == "cancelled":
            lines.append("Order cancelled. If a charge remains, I can check billing.")

        return AgentResult(
            agent_name=self.name,
            content="\n".join(lines),
            confidence=0.92,
            data={
                "found": True,
                "order": order,
                "status": status_key,
                "status_label": status_label,
                "statuses": ["Delivered", "Delayed", "Returned", "Cancelled"],
            },
        )
