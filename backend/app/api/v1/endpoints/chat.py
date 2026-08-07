"""Chat API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, get_db_optional
from app.db.models.user import User
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/message", response_model=ChatMessageResponse)
@router.post("", response_model=ChatMessageResponse, include_in_schema=False)
async def send_message(
    payload: ChatMessageRequest,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> ChatMessageResponse:
    """Send a customer message through the Master Agent orchestration graph."""
    customer_id = str(user.id) if user else None
    return await chat_service.handle_message(
        payload, customer_id=customer_id, db=db
    )
