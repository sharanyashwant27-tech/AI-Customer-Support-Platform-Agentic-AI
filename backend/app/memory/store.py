"""Conversation, customer profile, and long-term memory interfaces."""

from abc import ABC, abstractmethod
from typing import Any


class MemoryStore(ABC):
    @abstractmethod
    async def get(self, key: str) -> Any:
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        ...

    @abstractmethod
    async def append(self, key: str, value: Any) -> None:
        ...


class InMemoryStore(MemoryStore):
    """Process-local memory used until Redis-backed stores are wired."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self._data.get(key)

    async def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        self._data[key] = value

    async def append(self, key: str, value: Any) -> None:
        current = self._data.get(key)
        if current is None:
            self._data[key] = [value]
        elif isinstance(current, list):
            current.append(value)
        else:
            self._data[key] = [current, value]
