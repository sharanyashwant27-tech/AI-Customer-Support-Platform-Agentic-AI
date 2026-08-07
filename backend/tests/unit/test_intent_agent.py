"""Intent agent unit tests."""

import pytest

from app.agents.intent.agent import IntentClassificationAgent


@pytest.mark.asyncio
async def test_order_intent():
    agent = IntentClassificationAgent()
    result = await agent.run({"user_message": "Where is my order tracking?"})
    assert result.data["intent"] == "order_status"
    assert result.confidence > 0.5


@pytest.mark.asyncio
async def test_escalation_intent():
    agent = IntentClassificationAgent()
    result = await agent.run({"user_message": "I want to speak to a human agent"})
    assert result.data["intent"] == "escalation"
