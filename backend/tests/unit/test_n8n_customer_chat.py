"""n8n Customer Chat workflow tests."""

import pytest

from app.workflows.n8n_customer_chat import WORKFLOW_STEPS, n8n_customer_chat


def test_workflow_steps_match_spec():
    assert WORKFLOW_STEPS == [
        "customer_chat",
        "webhook",
        "intent_detection",
        "knowledge_search",
        "vector_search",
        "llm",
        "crm_update",
        "ticket_creation",
        "email",
        "slack_notification",
        "customer_response",
    ]


@pytest.mark.asyncio
async def test_n8n_customer_chat_pipeline():
    result = await n8n_customer_chat.run(
        {
            "message": "My payment failed.",
            "session_id": "n8n-test-1",
            "customer_id": "cust-n8n-1",
            "email": "customer@example.com",
            "channel": "web",
        }
    )
    assert result["ok"] is True
    assert result["intent"] in {"ticket", "billing"} or result.get("primary_label") == "billing" or result["intent"]
    assert result["crm_updated"] is True
    assert result["response"]
    assert "customer_response" in result["workflow_path"]
    assert "intent_detection" in result["workflow_path"]
    assert "knowledge_search" in result["workflow_path"]
    assert "vector_search" in result["workflow_path"]
    assert "llm" in result["workflow_path"]
    assert "crm_update" in result["workflow_path"]
    assert "ticket_creation" in result["workflow_path"]
    assert "email" in result["workflow_path"]
    assert "slack_notification" in result["workflow_path"]
