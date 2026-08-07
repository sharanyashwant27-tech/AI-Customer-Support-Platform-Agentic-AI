"""Multi-channel inbound webhooks: WhatsApp, Voice, Email, Slack, Teams."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_optional
from app.channels.base import Channel, ChannelMessage
from app.core.config import get_settings
from app.services.support_service import support_service

router = APIRouter(prefix="/channels", tags=["channels"])


class InboundMessage(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    customer_id: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    language: str | None = None
    external_thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_channels() -> dict[str, Any]:
    return {
        "channels": [c.value for c in Channel],
        "capabilities": {
            "web": ["chat", "tickets", "orders", "knowledge"],
            "email": ["inbound", "outbound"],
            "whatsapp": ["inbound", "outbound"],
            "voice": ["stt_webhook", "tts_outbound"],
            "slack": ["events", "alerts"],
            "teams": ["webhook", "alerts"],
        },
    }


@router.post("/{channel_name}/message")
async def channel_message(
    channel_name: str,
    payload: InboundMessage,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> dict[str, Any]:
    try:
        channel = Channel(channel_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {channel_name}") from exc

    message = ChannelMessage(
        text=payload.text,
        channel=channel,
        session_id=payload.session_id,
        customer_id=payload.customer_id,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        language=payload.language,
        external_thread_id=payload.external_thread_id,
        metadata=payload.metadata,
    )
    reply = await support_service.handle_channel_message(message, db=db)
    return reply.model_dump()


# --- WhatsApp (Meta-style verify + inbound) ---


@router.get("/whatsapp/webhook")
async def whatsapp_verify(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Any:
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return int(hub_challenge or 0)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_inbound(
    request: Request,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> dict[str, str]:
    body = await request.json()
    # Support both Meta Cloud API shape and simplified payload
    text = ""
    phone = None
    session_id = None
    try:
        entry = (body.get("entry") or [{}])[0]
        changes = (entry.get("changes") or [{}])[0]
        value = changes.get("value") or {}
        messages = value.get("messages") or []
        if messages:
            msg = messages[0]
            text = (msg.get("text") or {}).get("body") or msg.get("body") or ""
            phone = msg.get("from")
            session_id = f"wa-{phone}"
    except Exception:
        text = body.get("text") or body.get("message") or ""
        phone = body.get("from") or body.get("customer_phone")
        session_id = body.get("session_id") or (f"wa-{phone}" if phone else None)

    if not text:
        return {"status": "ignored"}

    message = ChannelMessage(
        text=text,
        channel=Channel.WHATSAPP,
        session_id=session_id,
        customer_phone=phone,
        metadata={"raw": body, "customer_phone": phone, "from": phone},
    )
    await support_service.handle_channel_message(message, db=db)
    return {"status": "ok"}


# --- Email inbound ---


@router.post("/email/inbound")
async def email_inbound(
    payload: dict[str, Any],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> dict[str, Any]:
    text = payload.get("text") or payload.get("body") or payload.get("subject") or ""
    if not text:
        raise HTTPException(status_code=400, detail="Missing email body")
    email = payload.get("from") or payload.get("customer_email")
    message = ChannelMessage(
        text=str(text),
        channel=Channel.EMAIL,
        session_id=payload.get("session_id") or (f"email-{email}" if email else None),
        customer_email=email,
        language=payload.get("language"),
        external_thread_id=payload.get("message_id"),
        metadata={
            "subject": payload.get("subject"),
            "customer_email": email,
            "from": email,
        },
    )
    reply = await support_service.handle_channel_message(message, db=db)
    return reply.model_dump()


# --- Voice (STT result → agent → TTS queue) ---


@router.post("/voice/utterance")
async def voice_utterance(
    payload: dict[str, Any],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> dict[str, Any]:
    text = payload.get("transcript") or payload.get("text") or ""
    if not text:
        raise HTTPException(status_code=400, detail="Missing transcript")
    message = ChannelMessage(
        text=str(text),
        channel=Channel.VOICE,
        session_id=payload.get("session_id") or payload.get("call_id"),
        language=payload.get("language"),
        customer_phone=payload.get("from"),
        metadata={
            "call_id": payload.get("call_id"),
            "customer_phone": payload.get("from"),
            "stt_confidence": payload.get("confidence"),
        },
    )
    reply = await support_service.handle_channel_message(message, db=db)
    return {
        "reply": reply.text,
        "language": reply.language,
        "session_id": reply.session_id,
        "tts": reply.metadata.get("outbound"),
        "handoff_required": reply.handoff_required,
    }


# --- Slack Events API ---


@router.post("/slack/events")
async def slack_events(
    request: Request,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> Any:
    body = await request.json()
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    event = body.get("event") or {}
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"status": "ignored"}

    text = event.get("text") or body.get("text") or ""
    if not text:
        return {"status": "ignored"}

    user = event.get("user")
    channel = event.get("channel")
    message = ChannelMessage(
        text=text,
        channel=Channel.SLACK,
        session_id=f"slack-{channel}-{user}",
        external_thread_id=event.get("ts"),
        metadata={
            "slack_channel": channel,
            "slack_user": user,
            "thread_ts": event.get("thread_ts") or event.get("ts"),
        },
    )
    reply = await support_service.handle_channel_message(message, db=db)
    return {"status": "ok", "session_id": reply.session_id}


# --- Microsoft Teams webhook ---


@router.post("/teams/webhook")
async def teams_webhook(
    payload: dict[str, Any],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> dict[str, Any]:
    text = (
        payload.get("text")
        or (payload.get("message") or {}).get("text")
        or payload.get("body")
        or ""
    )
    if isinstance(text, dict):
        text = text.get("content") or ""
    if not text:
        raise HTTPException(status_code=400, detail="Missing Teams message text")

    conversation_id = (
        (payload.get("conversation") or {}).get("id")
        or payload.get("conversation_id")
    )
    message = ChannelMessage(
        text=str(text),
        channel=Channel.TEAMS,
        session_id=f"teams-{conversation_id}" if conversation_id else None,
        external_thread_id=conversation_id,
        metadata={"teams_conversation_id": conversation_id, "raw_type": payload.get("type")},
    )
    reply = await support_service.handle_channel_message(message, db=db)
    return {
        "type": "message",
        "text": reply.text,
        "session_id": reply.session_id,
    }
