"""Feedback API with PostgreSQL persistence and prompt optimizer hooks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_optional
from app.db.repositories.entities import feedback_repo
from app.prompts.registry import prompt_optimizer
from app.schemas.common import FeedbackCreate, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])

_FALLBACK: list[FeedbackResponse] = []


@router.post("", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    payload: FeedbackCreate,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> FeedbackResponse:
    variant = payload.category or "master_system"
    prompt_optimizer.record(variant, payload.rating)

    if db is not None:
        try:
            item = await feedback_repo.create(
                db,
                rating=payload.rating,
                comment=payload.comment,
                category=payload.category,
                customer_id=payload.customer_id,
                chat_history_id=payload.chat_history_id or payload.message_id,
                session_id=payload.session_id,
                agent_name=payload.agent_name,
            )
            return FeedbackResponse.model_validate(item)
        except Exception:
            pass

    item = FeedbackResponse(
        id=uuid.uuid4(),
        rating=payload.rating,
        comment=payload.comment,
        category=payload.category,
        session_id=payload.session_id,
        chat_history_id=payload.chat_history_id or payload.message_id,
        customer_id=payload.customer_id,
        agent_name=payload.agent_name,
        created_at=datetime.now(UTC),
    )
    _FALLBACK.append(item)
    return item


@router.get("", response_model=list[FeedbackResponse])
async def list_feedback(
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> list[FeedbackResponse]:
    if db is not None:
        try:
            items = await feedback_repo.list_all(db)
            return [FeedbackResponse.model_validate(i) for i in items]
        except Exception:
            pass
    return _FALLBACK


@router.get("/prompt-optimization")
async def prompt_optimization_status() -> dict:
    candidates = ["master_system", "master_system_b"]
    return {
        "best_variant": prompt_optimizer.best_variant(candidates),
        "suggested_weights": prompt_optimizer.suggest_weights(candidates),
        "scores": prompt_optimizer.scores,
    }
