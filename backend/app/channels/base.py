"""Multi-channel message model shared across chat, email, WhatsApp, voice, Slack, Teams."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Channel(str, Enum):
    WEB = "web"
    CHAT = "chat"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    VOICE = "voice"
    SLACK = "slack"
    TEAMS = "teams"


class ChannelMessage(BaseModel):
    """Normalized inbound message from any support channel."""

    text: str = Field(min_length=1, max_length=8000)
    channel: Channel = Channel.WEB
    session_id: str | None = None
    customer_id: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    language: str | None = None
    external_thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelReply(BaseModel):
    """Normalized outbound reply ready for channel adapters."""

    text: str
    channel: Channel
    session_id: str
    language: str = "en"
    handoff_required: bool = False
    intent: str | None = None
    sentiment: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
