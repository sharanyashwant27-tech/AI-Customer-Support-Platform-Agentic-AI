"""Order lookup API — sample dataset backed."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.common import OrderLookupRequest, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])

_SAMPLE_PATH = (
    Path(__file__).resolve().parents[5] / "sample_data" / "orders" / "sample_orders.json"
)
# parents: endpoints -> v1 -> api -> app -> backend -> project root
_SAMPLE_PATH = Path(__file__).resolve().parents[5] / "sample_data" / "orders" / "sample_orders.json"


def _load_orders() -> list[dict]:
    if _SAMPLE_PATH.exists():
        return json.loads(_SAMPLE_PATH.read_text(encoding="utf-8"))
    return [
        {
            "order_id": "ORD-1001",
            "status": "shipped",
            "customer_email": "customer@example.com",
            "items": [
                {
                    "sku": "SKU-01",
                    "name": "Wireless Headphones",
                    "quantity": 1,
                    "unit_price": 129.99,
                }
            ],
            "total": 129.99,
            "currency": "USD",
            "placed_at": "2026-08-01T10:00:00Z",
            "estimated_delivery": "2026-08-08T18:00:00Z",
            "tracking_number": "1Z999AA10123456784",
            "shipping_address": {"city": "San Francisco", "country": "US"},
        }
    ]


@router.post("/lookup", response_model=OrderResponse)
async def lookup_order(payload: OrderLookupRequest) -> OrderResponse:
    orders = _load_orders()
    for order in orders:
        if payload.order_id and order["order_id"] == payload.order_id:
            return OrderResponse(**order)
        if payload.tracking_number and order.get("tracking_number") == payload.tracking_number:
            return OrderResponse(**order)
        if payload.email and order["customer_email"].lower() == payload.email.lower():
            return OrderResponse(**order)
    raise HTTPException(status_code=404, detail="Order not found")


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    return await lookup_order(OrderLookupRequest(order_id=order_id))
