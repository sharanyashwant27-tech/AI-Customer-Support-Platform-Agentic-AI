"""Recommendation Agent — products, coupons, offers, upgrades."""

from __future__ import annotations

from app.agents.shared.base import AgentName, AgentResult, AgentState, BaseAgent

PRODUCTS = [
    {
        "type": "product",
        "sku": "SKU-WH-01",
        "name": "Wireless Headphones Pro",
        "reason": "Top-rated for travel and remote work",
    },
    {
        "type": "product",
        "sku": "SKU-KB-02",
        "name": "Mechanical Keyboard",
        "reason": "Pairs well with productivity setups",
    },
    {
        "type": "upgrade",
        "sku": "SKU-WH-01-PLUS",
        "name": "Headphones Pro → Elite Upgrade",
        "reason": "Noise cancelling + extended warranty",
    },
]

COUPONS = [
    {
        "type": "coupon",
        "code": "SAVE15",
        "name": "15% off accessories",
        "reason": "Available for support goodwill",
    },
    {
        "type": "coupon",
        "code": "SHIPFREE",
        "name": "Free express shipping",
        "reason": "Useful after a delayed delivery",
    },
]

OFFERS = [
    {
        "type": "offer",
        "name": "Replacement at no charge",
        "reason": "For delayed or defective shipments",
    },
    {
        "type": "offer",
        "name": "Priority support for 30 days",
        "reason": "After an escalated complaint",
    },
]


class RecommendationAgent(BaseAgent):
    """Suggests products, coupons, offers, and upgrades."""

    name = AgentName.RECOMMENDATION

    async def run(self, state: AgentState) -> AgentResult:
        message = (state.get("user_message") or "").lower()
        intent = state.get("intent") or ""
        sentiment = state.get("sentiment") or "neutral"

        picks: list[dict] = []

        if intent in {"shipping", "package_delay", "order_status"} or "delay" in message:
            picks.extend([COUPONS[1], OFFERS[0], PRODUCTS[0]])
        elif intent == "refund" or "refund" in message:
            picks.extend([OFFERS[0], COUPONS[0], OFFERS[1]])
        elif "upgrade" in message or "elite" in message:
            picks.extend([PRODUCTS[2], PRODUCTS[0], COUPONS[0]])
        elif "keyboard" in message:
            picks.extend([PRODUCTS[1], COUPONS[0], PRODUCTS[2]])
        elif "coupon" in message or "discount" in message or "offer" in message:
            picks.extend([COUPONS[0], COUPONS[1], OFFERS[1]])
        else:
            picks.extend([PRODUCTS[0], PRODUCTS[1], COUPONS[0]])

        if sentiment in {"angry", "frustrated", "urgent"}:
            # Lead with goodwill offer
            picks = [OFFERS[1], COUPONS[0]] + [p for p in picks if p not in OFFERS]

        # de-dupe preserving order
        seen: set[str] = set()
        unique = []
        for p in picks:
            key = p.get("code") or p.get("sku") or p["name"]
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)

        lines = []
        for p in unique[:4]:
            tag = p["type"].upper()
            code = f" `{p['code']}`" if p.get("code") else ""
            lines.append(f"- [{tag}] {p['name']}{code} — {p['reason']}")

        labels = [p["name"] for p in unique[:4]]
        return AgentResult(
            agent_name=self.name,
            content="Suggestions for you:\n" + "\n".join(lines),
            confidence=0.84,
            data={
                "recommendations": labels,
                "items": unique[:4],
                "categories": ["products", "coupons", "offers", "upgrades"],
            },
        )
