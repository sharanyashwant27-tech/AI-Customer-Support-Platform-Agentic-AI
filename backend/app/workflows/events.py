"""RabbitMQ event publisher for async workflows (n8n, workers, alerts)."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EXCHANGE_NAME = "aics.events"
ROUTING_KEYS = {
    "ticket.created": "ticket.created",
    "handoff.requested": "handoff.requested",
    "refund.offered": "refund.offered",
    "package.delayed": "package.delayed",
    "chat.message": "chat.message",
    "crm.updated": "crm.updated",
}


class EventPublisher:
    """Publish JSON events to RabbitMQ; no-ops gracefully when broker is down."""

    def __init__(self) -> None:
        self._connection = None
        self._channel = None

    async def connect(self) -> bool:
        if self._channel is not None:
            return True
        settings = get_settings()
        try:
            import aio_pika

            self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            self._channel = await self._connection.channel()
            await self._channel.declare_exchange(
                EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
            )
            logger.info("rabbitmq_connected", host=settings.rabbitmq_host)
            return True
        except Exception as exc:
            logger.warning("rabbitmq_unavailable", error=str(exc))
            self._connection = None
            self._channel = None
            return False

    async def publish(self, event_type: str, payload: dict[str, Any]) -> bool:
        routing_key = ROUTING_KEYS.get(event_type, event_type)
        body = json.dumps(
            {"event": event_type, "payload": payload},
            default=str,
        ).encode("utf-8")
        if not await self.connect():
            logger.info("rabbitmq_event_dropped", event_type=event_type)
            return False
        try:
            import aio_pika

            exchange = await self._channel.get_exchange(EXCHANGE_NAME)
            await exchange.publish(
                aio_pika.Message(
                    body=body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=routing_key,
            )
            logger.info("rabbitmq_published", event_type=event_type, routing_key=routing_key)
            return True
        except Exception as exc:
            logger.warning("rabbitmq_publish_failed", event_type=event_type, error=str(exc))
            self._channel = None
            self._connection = None
            return False

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._channel = None


event_publisher = EventPublisher()
