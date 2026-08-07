"""n8n workflow step endpoints — Customer Chat pipeline."""

from typing import Any

from fastapi import APIRouter

from app.workflows.n8n_customer_chat import WORKFLOW_STEPS, n8n_customer_chat

router = APIRouter(prefix="/workflows/n8n", tags=["n8n-workflows"])


@router.get("/customer-chat")
async def customer_chat_info() -> dict[str, Any]:
    return {
        "workflow": "n8n_customer_chat",
        "webhook_path": "aics-customer-chat",
        "steps": WORKFLOW_STEPS,
        "diagram": (
            "Customer Chat → Webhook → Intent Detection → Knowledge Search → "
            "Vector Search → LLM → CRM Update → Ticket Creation → Email → "
            "Slack Notification → Customer Response"
        ),
        "step_endpoints": {
            "intent": "POST /api/v1/workflows/n8n/steps/intent",
            "knowledge": "POST /api/v1/workflows/n8n/steps/knowledge",
            "vector": "POST /api/v1/workflows/n8n/steps/vector",
            "llm": "POST /api/v1/workflows/n8n/steps/llm",
            "crm": "POST /api/v1/workflows/n8n/steps/crm",
            "ticket": "POST /api/v1/workflows/n8n/steps/ticket",
            "email": "POST /api/v1/workflows/n8n/steps/email",
            "slack": "POST /api/v1/workflows/n8n/steps/slack",
            "response": "POST /api/v1/workflows/n8n/steps/response",
            "run_all": "POST /api/v1/workflows/n8n/customer-chat",
        },
    }


@router.post("/customer-chat")
async def run_customer_chat(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Full pipeline (also used as the FastAPI stand-in when n8n is offline).

    Body: { "message": "...", "session_id"?, "customer_id"?, "email"?, "channel"? }
    """
    return await n8n_customer_chat.run(payload)


@router.post("/steps/intent")
async def step_intent(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.intent_detection(payload)


@router.post("/steps/knowledge")
async def step_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.knowledge_search(payload)


@router.post("/steps/vector")
async def step_vector(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.vector_search(payload)


@router.post("/steps/llm")
async def step_llm(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.llm(payload)


@router.post("/steps/crm")
async def step_crm(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.crm_update(payload)


@router.post("/steps/ticket")
async def step_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.ticket_creation(payload)


@router.post("/steps/email")
async def step_email(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.email_notify(payload)


@router.post("/steps/slack")
async def step_slack(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.slack_notification(payload)


@router.post("/steps/response")
async def step_response(payload: dict[str, Any]) -> dict[str, Any]:
    return await n8n_customer_chat.customer_response(payload)
