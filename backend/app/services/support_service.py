"""Unified support orchestration across all channels with i18n."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.master.graph import get_master_agent
from app.channels.base import Channel, ChannelMessage, ChannelReply
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.conversation import MessageRole
from app.db.repositories.entities import conversation_repo
from app.i18n.language import language_service
from app.integrations.hub import integration_hub
from app.observability.metrics import CHAT_MESSAGES_TOTAL
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse, Citation
from app.services.ticket_service import extract_ticket_draft, persist_agent_ticket_draft

logger = get_logger(__name__)


class SupportService:
    """Channel-agnostic entrypoint used by web chat and external adapters."""

    async def handle_channel_message(
        self,
        message: ChannelMessage,
        *,
        db: AsyncSession | None = None,
        dispatch_outbound: bool = True,
    ) -> ChannelReply:
        settings = get_settings()
        session_id = message.session_id or str(uuid.uuid4())
        lang_hint = message.language
        original = message.text

        if settings.enable_auto_translate:
            lang_result = await language_service.to_english(
                original, language=lang_hint
            )
            working_text = lang_result.translated_text
            language = lang_result.language
        else:
            working_text = original
            language = lang_hint or settings.default_language

        meta: dict[str, Any] = {
            **message.metadata,
            "channel": message.channel.value,
            "language": language,
            "original_message": original,
            "customer_email": message.customer_email,
            "customer_phone": message.customer_phone,
            "external_thread_id": message.external_thread_id,
        }
        if message.customer_email:
            meta["email"] = message.customer_email

        master = get_master_agent()
        result = await master.process(
            user_message=working_text,
            session_id=session_id,
            customer_id=message.customer_id,
            metadata=meta,
        )

        reply_en = result.get("final_response") or "I'm here to help."
        if settings.enable_auto_translate and language != "en":
            reply_text = await language_service.from_english(
                reply_en, language=language
            )
        else:
            reply_text = reply_en

        intent = result.get("intent")
        handoff = bool(result.get("handoff_required"))
        CHAT_MESSAGES_TOTAL.labels(
            intent=intent or "unknown",
            handoff=str(handoff).lower(),
        ).inc()

        citations_raw = result.get("citations") or []
        result_meta = dict(result.get("metadata") or {})
        result_meta.update(
            {
                "language": language,
                "channel": message.channel.value,
                "agents_used": result.get("agents_used"),
                "confidence": result.get("confidence"),
                "recommendations": result.get("recommendations") or [],
            }
        )

        # Persist Ticket Agent / playbook drafts into PostgreSQL
        draft = extract_ticket_draft(result.get("agent_results") or {})
        if draft:
            try:
                saved = await persist_agent_ticket_draft(
                    draft,
                    db=db,
                    customer_id=message.customer_id,
                    customer_email=message.customer_email,
                )
                if saved:
                    result_meta["ticket"] = {
                        "id": str(saved.id),
                        "ticket_number": saved.ticket_number,
                        "subject": saved.subject,
                        "status": saved.status.value,
                        "priority": saved.priority.value,
                        "category": saved.category,
                    }
                    # Prefer the persisted number in the reply if agent used a draft id
                    if saved.ticket_number and saved.ticket_number not in reply_en:
                        result_meta["ticket_created"] = True
            except Exception as exc:
                logger.warning("ticket_persist_from_chat_failed", error=str(exc))

        conversation_id = None
        message_id = None
        if db is not None:
            try:
                from app.db.repositories.entities import customer_repo

                cust_uuid = None
                if message.customer_id:
                    try:
                        cust_uuid = uuid.UUID(message.customer_id)
                    except ValueError:
                        customer = await customer_repo.get_or_create(
                            db,
                            email=f"{message.customer_id}@customers.local",
                            full_name=str(message.customer_id),
                            external_id=str(message.customer_id),
                        )
                        cust_uuid = customer.id
                conversation = await conversation_repo.get_or_create(
                    db,
                    session_id=session_id,
                    customer_id=cust_uuid,
                    channel=message.channel.value,
                    metadata=meta,
                )
                await conversation_repo.add_message(
                    db,
                    conversation=conversation,
                    role=MessageRole.USER,
                    content=original,
                    intent=intent,
                    metadata={"language": language},
                )
                assistant = await conversation_repo.add_message(
                    db,
                    conversation=conversation,
                    role=MessageRole.ASSISTANT,
                    content=reply_text,
                    intent=intent,
                    confidence=result.get("confidence"),
                    agent_name="master",
                    citations=citations_raw if isinstance(citations_raw, list) else [],
                    metadata=result_meta,
                )
                conversation_id = conversation.id
                message_id = assistant.id
                result_meta["conversation_id"] = str(conversation_id)
                result_meta["message_id"] = str(message_id)
                await db.commit()
            except Exception as exc:
                logger.warning("channel_persist_failed", error=str(exc))

        reply = ChannelReply(
            text=reply_text,
            channel=message.channel,
            session_id=session_id,
            language=language,
            handoff_required=handoff,
            intent=intent,
            sentiment=result.get("sentiment"),
            citations=[c for c in citations_raw if isinstance(c, dict)],
            metadata=result_meta,
        )

        if dispatch_outbound and message.channel not in {Channel.WEB, Channel.CHAT}:
            outbound = await integration_hub.dispatch(reply)
            reply.metadata["outbound"] = outbound
        elif handoff:
            # Always alert Slack/Teams on handoff regardless of channel
            await integration_hub.notify_slack(reply)
            await integration_hub.notify_teams(reply)

        return reply

    async def handle_web_chat(
        self,
        payload: ChatMessageRequest,
        *,
        customer_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> ChatMessageResponse:
        channel = Channel(payload.channel) if payload.channel in Channel._value2member_map_ else Channel.WEB
        message = ChannelMessage(
            text=payload.message,
            channel=channel,
            session_id=payload.session_id,
            customer_id=customer_id,
            language=payload.metadata.get("language") if payload.metadata else None,
            customer_email=payload.metadata.get("email") if payload.metadata else None,
            customer_phone=payload.metadata.get("phone") if payload.metadata else None,
            metadata=payload.metadata,
        )
        reply = await self.handle_channel_message(
            message, db=db, dispatch_outbound=False
        )
        citations = [
            Citation(**c) if "source" in c else Citation(source=str(c))
            for c in reply.citations
        ]
        conv_id = reply.metadata.get("conversation_id")
        msg_id = reply.metadata.get("message_id")
        return ChatMessageResponse(
            session_id=reply.session_id,
            conversation_id=uuid.UUID(conv_id) if conv_id else None,
            message_id=uuid.UUID(msg_id) if msg_id else None,
            reply=reply.text,
            intent=reply.intent,
            confidence=(reply.metadata or {}).get("confidence"),
            agent_name="master",
            agents_used=list((reply.metadata or {}).get("agents_used") or []),
            citations=citations,
            handoff_required=reply.handoff_required,
            sentiment=reply.sentiment,
            recommendations=list((reply.metadata or {}).get("recommendations") or []),
            metadata=reply.metadata,
            language=reply.language,
            channel=reply.channel.value,
            created_at=datetime.now(UTC),
        )


support_service = SupportService()
