"""Redis-backed memory with resilient in-process fallback."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.memory.store import InMemoryStore, MemoryStore

logger = get_logger(__name__)


class RedisMemoryStore(MemoryStore):
    def __init__(self) -> None:
        import redis.asyncio as redis

        settings = get_settings()
        self._client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )

    async def get(self, key: str) -> Any:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        payload = json.dumps(value, default=str)
        if ttl_seconds:
            await self._client.set(key, payload, ex=ttl_seconds)
        else:
            await self._client.set(key, payload)

    async def append(self, key: str, value: Any) -> None:
        current = await self.get(key)
        if current is None:
            await self.set(key, [value])
        elif isinstance(current, list):
            current.append(value)
            await self.set(key, current)
        else:
            await self.set(key, [current, value])

    async def ping(self) -> bool:
        return bool(await self._client.ping())


class ResilientMemoryStore(MemoryStore):
    """Prefer Redis; permanently fall back to in-memory after first failure."""

    def __init__(self, primary: MemoryStore, fallback: MemoryStore) -> None:
        self.primary = primary
        self.fallback = fallback
        self._failed = False

    async def get(self, key: str) -> Any:
        if not self._failed:
            try:
                return await self.primary.get(key)
            except Exception as exc:
                logger.warning("memory_primary_failed", op="get", error=str(exc))
                self._failed = True
        return await self.fallback.get(key)

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        if not self._failed:
            try:
                await self.primary.set(key, value, ttl_seconds=ttl_seconds)
                return
            except Exception as exc:
                logger.warning("memory_primary_failed", op="set", error=str(exc))
                self._failed = True
        await self.fallback.set(key, value, ttl_seconds=ttl_seconds)

    async def append(self, key: str, value: Any) -> None:
        if not self._failed:
            try:
                await self.primary.append(key, value)
                return
            except Exception as exc:
                logger.warning("memory_primary_failed", op="append", error=str(exc))
                self._failed = True
        await self.fallback.append(key, value)


class ConversationMemory:
    """
    Maintain:
    - Conversation Memory
    - Customer Profile
    - Purchase History
    - Previous Tickets
    - Preferences
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def _conv_key(self, session_id: str) -> str:
        return f"aics:conv:{session_id}"

    def _profile_key(self, customer_id: str) -> str:
        return f"aics:profile:{customer_id}"

    def _long_term_key(self, customer_id: str) -> str:
        return f"aics:ltm:{customer_id}"

    def _purchases_key(self, customer_id: str) -> str:
        return f"aics:purchases:{customer_id}"

    def _tickets_key(self, customer_id: str) -> str:
        return f"aics:tickets:{customer_id}"

    def _prefs_key(self, customer_id: str) -> str:
        return f"aics:prefs:{customer_id}"

    async def add_turn(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.store.append(
            self._conv_key(session_id),
            {"role": role, "content": content, "metadata": metadata or {}},
        )
        history = await self.get_history(session_id)
        await self.store.set(
            self._conv_key(session_id), history, ttl_seconds=7 * 24 * 3600
        )

    async def get_history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        data = await self.store.get(self._conv_key(session_id))
        if not data:
            return []
        if isinstance(data, list):
            return data[-limit:]
        return []

    async def summarize_conversation(
        self, session_id: str, *, limit: int = 8
    ) -> str:
        history = await self.get_history(session_id, limit=limit)
        if not history:
            return "No prior conversation turns."
        lines = []
        for turn in history:
            role = turn.get("role", "user")
            content = str(turn.get("content") or "")[:160]
            lines.append(f"- {role}: {content}")
        return "Conversation so far:\n" + "\n".join(lines)

    async def update_profile(self, customer_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        profile = await self.store.get(self._profile_key(customer_id)) or {}
        if not isinstance(profile, dict):
            profile = {}
        profile.update(patch)
        await self.store.set(
            self._profile_key(customer_id), profile, ttl_seconds=30 * 24 * 3600
        )
        return profile

    async def get_profile(self, customer_id: str) -> dict[str, Any]:
        data = await self.store.get(self._profile_key(customer_id))
        return data if isinstance(data, dict) else {}

    async def set_purchase_history(
        self, customer_id: str, purchases: list[dict[str, Any]]
    ) -> None:
        await self.store.set(
            self._purchases_key(customer_id), purchases, ttl_seconds=30 * 24 * 3600
        )

    async def get_purchase_history(self, customer_id: str) -> list[dict[str, Any]]:
        data = await self.store.get(self._purchases_key(customer_id))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    async def set_previous_tickets(
        self, customer_id: str, tickets: list[dict[str, Any]]
    ) -> None:
        await self.store.set(
            self._tickets_key(customer_id), tickets, ttl_seconds=30 * 24 * 3600
        )

    async def get_previous_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        data = await self.store.get(self._tickets_key(customer_id))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    async def remember_ticket(self, customer_id: str, ticket: dict[str, Any]) -> None:
        tickets = await self.get_previous_tickets(customer_id)
        number = ticket.get("ticket_number")
        if number:
            tickets = [t for t in tickets if t.get("ticket_number") != number]
        tickets.append(ticket)
        await self.set_previous_tickets(customer_id, tickets[-20:])

    async def set_preferences(
        self, customer_id: str, preferences: dict[str, Any]
    ) -> dict[str, Any]:
        current = await self.get_preferences(customer_id)
        current.update(preferences)
        await self.store.set(
            self._prefs_key(customer_id), current, ttl_seconds=90 * 24 * 3600
        )
        return current

    async def get_preferences(self, customer_id: str) -> dict[str, Any]:
        data = await self.store.get(self._prefs_key(customer_id))
        return data if isinstance(data, dict) else {}

    async def remember_long_term(self, customer_id: str, fact: str) -> None:
        await self.store.append(self._long_term_key(customer_id), fact)

    async def get_long_term(self, customer_id: str) -> list[str]:
        data = await self.store.get(self._long_term_key(customer_id))
        if isinstance(data, list):
            return [str(x) for x in data]
        return []

    async def get_customer_memory_bundle(
        self,
        *,
        customer_id: str | None,
        session_id: str,
    ) -> dict[str, Any]:
        """Full memory package for prompt context."""
        conversation = await self.get_history(session_id, limit=8)
        summary = await self.summarize_conversation(session_id)
        if not customer_id:
            return {
                "conversation_memory": conversation,
                "conversation_summary": summary,
                "customer_profile": {},
                "purchase_history": [],
                "previous_tickets": [],
                "preferences": {},
                "long_term_memory": [],
            }

        profile = await self.get_profile(customer_id)
        purchases = await self.get_purchase_history(customer_id)
        tickets = await self.get_previous_tickets(customer_id)
        prefs = await self.get_preferences(customer_id)
        long_term = await self.get_long_term(customer_id)

        # Seed lightweight demo memory when empty
        if not purchases:
            purchases = [
                {
                    "order_id": "ORD-1001",
                    "product": "Wireless Headphones Pro",
                    "status": "shipped",
                }
            ]
            await self.set_purchase_history(customer_id, purchases)
        if not prefs:
            prefs = await self.set_preferences(
                customer_id,
                {
                    "channel": "web",
                    "language": "en",
                    "contact_method": "email",
                },
            )
        if not profile:
            profile = await self.update_profile(
                customer_id,
                {"customer_id": customer_id, "tier": "standard"},
            )

        return {
            "conversation_memory": conversation,
            "conversation_summary": summary,
            "customer_profile": profile,
            "purchase_history": purchases,
            "previous_tickets": tickets,
            "preferences": prefs,
            "long_term_memory": long_term,
        }

    def format_memory_block(self, bundle: dict[str, Any]) -> str:
        parts: list[str] = []
        if bundle.get("conversation_summary"):
            parts.append(str(bundle["conversation_summary"]))
        profile = bundle.get("customer_profile") or {}
        if profile:
            parts.append(f"Customer profile: {profile}")
        purchases = bundle.get("purchase_history") or []
        if purchases:
            parts.append(
                "Purchase history: "
                + "; ".join(
                    f"{p.get('order_id')} {p.get('product')} ({p.get('status')})"
                    for p in purchases[:5]
                )
            )
        tickets = bundle.get("previous_tickets") or []
        if tickets:
            parts.append(
                "Previous tickets: "
                + "; ".join(
                    f"{t.get('ticket_number')} [{t.get('status')}]"
                    for t in tickets[:5]
                )
            )
        prefs = bundle.get("preferences") or {}
        if prefs:
            parts.append(f"Preferences: {prefs}")
        ltm = bundle.get("long_term_memory") or []
        if ltm:
            parts.append("Long-term notes: " + "; ".join(str(x) for x in ltm[-5:]))
        return "\n".join(parts)


_memory: ConversationMemory | None = None
_memory_backend: str = "uninitialized"


async def _build_memory() -> ConversationMemory:
    settings = get_settings()
    fallback = InMemoryStore()
    try:
        store = RedisMemoryStore()
        if await store.ping():
            logger.info("memory_backend", backend="redis", host=settings.redis_host)
            return ConversationMemory(ResilientMemoryStore(store, fallback))
    except Exception as exc:
        logger.warning("redis_unavailable_using_memory", error=str(exc))
    logger.info("memory_backend", backend="in_memory")
    return ConversationMemory(fallback)


def get_conversation_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory(InMemoryStore())
        logger.info("memory_backend", backend="in_memory_bootstrap")
    return _memory


async def ensure_memory() -> ConversationMemory:
    global _memory, _memory_backend
    if _memory_backend in {"redis", "in_memory"}:
        return get_conversation_memory()
    _memory = await _build_memory()
    _memory_backend = (
        "redis"
        if isinstance(_memory.store, ResilientMemoryStore)
        else "in_memory"
    )
    return _memory


def reset_memory_for_tests() -> None:
    global _memory, _memory_backend
    _memory = ConversationMemory(InMemoryStore())
    _memory_backend = "in_memory"
