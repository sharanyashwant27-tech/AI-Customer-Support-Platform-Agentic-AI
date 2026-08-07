"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    advanced,
    auth,
    channels,
    chat,
    customers,
    feedback,
    health,
    knowledge,
    orders,
    tickets,
    workflows,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(channels.router)
api_router.include_router(customers.router)
api_router.include_router(tickets.router)
api_router.include_router(orders.router)
api_router.include_router(knowledge.router)
api_router.include_router(feedback.router)
api_router.include_router(workflows.router)
api_router.include_router(advanced.router)
