"""Chat orchestration — thin wrapper over SupportService."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.support_service import support_service


class ChatService:
    async def handle_message(
        self,
        payload: ChatMessageRequest,
        *,
        customer_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> ChatMessageResponse:
        return await support_service.handle_web_chat(
            payload, customer_id=customer_id, db=db
        )


chat_service = ChatService()
