"""Outbound integrations for Slack, Teams, WhatsApp, email, and voice."""

from __future__ import annotations

from typing import Any

import httpx

from app.channels.base import Channel, ChannelReply
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class IntegrationHub:
    """Fan-out replies and alerts to external collaboration / messaging systems."""

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not url:
            return {"status": "skipped", "reason": "webhook_not_configured"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(url, json=payload)
                return {
                    "status": "sent" if response.is_success else "error",
                    "code": response.status_code,
                    "body": response.text[:500],
                }
        except Exception as exc:
            logger.warning("integration_post_failed", url=url, error=str(exc))
            return {"status": "error", "error": str(exc)}

    async def notify_slack(
        self, reply: ChannelReply, *, channel: str | None = None
    ) -> dict[str, Any]:
        settings = get_settings()
        payload = {
            "text": reply.text,
            "channel": channel or settings.slack_default_channel,
            "session_id": reply.session_id,
            "intent": reply.intent,
            "sentiment": reply.sentiment,
            "handoff": reply.handoff_required,
        }
        # Prefer dedicated Slack webhook; fall back to n8n
        url = settings.slack_webhook_url or f"{settings.n8n_webhook_base_url}/aics-slack"
        result = await self._post(url, payload)
        logger.info("slack_notify", status=result.get("status"), session=reply.session_id)
        return result

    async def notify_teams(self, reply: ChannelReply) -> dict[str, Any]:
        settings = get_settings()
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"AICS support · {reply.intent or 'update'}",
            "themeColor": "1F6F5B",
            "title": "Customer Support Update",
            "text": reply.text,
            "sections": [
                {
                    "facts": [
                        {"name": "Session", "value": reply.session_id},
                        {"name": "Intent", "value": reply.intent or "—"},
                        {"name": "Sentiment", "value": reply.sentiment or "—"},
                        {
                            "name": "Handoff",
                            "value": "Yes" if reply.handoff_required else "No",
                        },
                    ]
                }
            ],
        }
        url = settings.teams_webhook_url or f"{settings.n8n_webhook_base_url}/aics-teams"
        return await self._post(url, payload)

    async def send_whatsapp(self, reply: ChannelReply, *, to_phone: str) -> dict[str, Any]:
        settings = get_settings()
        payload = {
            "to": to_phone,
            "type": "text",
            "text": {"body": reply.text[:4096]},
            "session_id": reply.session_id,
        }
        url = (
            settings.whatsapp_webhook_url
            or f"{settings.n8n_webhook_base_url}/aics-whatsapp"
        )
        return await self._post(url, payload)

    async def send_email(
        self,
        reply: ChannelReply,
        *,
        to_email: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        payload = {
            "to": to_email,
            "subject": subject
            or f"[{settings.app_name}] Re: {reply.intent or 'your request'}",
            "body": reply.text,
            "session_id": reply.session_id,
            "handoff": reply.handoff_required,
        }
        url = settings.email_webhook_url or f"{settings.n8n_webhook_base_url}/aics-email"
        return await self._post(url, payload)

    async def send_voice_tts(self, reply: ChannelReply) -> dict[str, Any]:
        """Queue text-to-speech for voice channel responses."""
        settings = get_settings()
        payload = {
            "text": reply.text,
            "language": reply.language,
            "session_id": reply.session_id,
            "voice": settings.voice_default_voice,
        }
        url = settings.voice_webhook_url or f"{settings.n8n_webhook_base_url}/aics-voice"
        return await self._post(url, payload)

    async def dispatch(self, reply: ChannelReply) -> dict[str, Any]:
        """Route outbound reply based on channel."""
        meta = reply.metadata or {}
        if reply.channel == Channel.SLACK:
            return await self.notify_slack(reply, channel=meta.get("slack_channel"))
        if reply.channel == Channel.TEAMS:
            return await self.notify_teams(reply)
        if reply.channel == Channel.WHATSAPP:
            phone = meta.get("customer_phone") or meta.get("from")
            if not phone:
                return {"status": "skipped", "reason": "missing_phone"}
            return await self.send_whatsapp(reply, to_phone=str(phone))
        if reply.channel == Channel.EMAIL:
            email = meta.get("customer_email") or meta.get("from")
            if not email:
                return {"status": "skipped", "reason": "missing_email"}
            return await self.send_email(
                reply, to_email=str(email), subject=meta.get("subject")
            )
        if reply.channel == Channel.VOICE:
            return await self.send_voice_tts(reply)
        return {"status": "local", "channel": reply.channel.value}


integration_hub = IntegrationHub()
