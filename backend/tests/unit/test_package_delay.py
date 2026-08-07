"""Package delay workflow tests."""

import pytest

from app.agents.intent.agent import IntentClassificationAgent
from app.agents.workflows.package_delay import PackageDelayWorkflow, is_package_delay_message


def test_detect_package_delay_phrase():
    assert is_package_delay_message("My package hasn't arrived.")
    assert is_package_delay_message("Still waiting on my delivery")
    assert not is_package_delay_message("What is your return policy?")


@pytest.mark.asyncio
async def test_intent_package_delay():
    agent = IntentClassificationAgent()
    result = await agent.run({"user_message": "My package hasn't arrived"})
    assert result.data["intent"] == "package_delay"


@pytest.mark.asyncio
async def test_package_delay_workflow_steps():
    agent = PackageDelayWorkflow()
    result = await agent.run(
        {
            "user_message": "My package hasn't arrived for ORD-1001",
            "sentiment": "angry",
        }
    )
    assert result.success
    steps = {s["step"] for s in result.data["steps"]}
    assert steps == {
        "check_order",
        "check_shipment",
        "check_delay",
        "explain_delay",
        "offer_refund",
        "create_ticket",
        "escalate_if_needed",
    }
    assert result.data["order"]["order_id"] == "ORD-1001"
    assert result.data["delay_days"] >= 1
    assert result.data["ticket"]["ticket_number"].startswith("TKT-")
    assert result.data["offer_refund"] is True
    assert result.data["escalate"] is True  # angry sentiment + delay
    assert "Order" in result.content
    assert "Shipment" in result.content
