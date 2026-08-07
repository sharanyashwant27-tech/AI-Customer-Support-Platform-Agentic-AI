"""Tests for language detection and refund agent."""

import pytest

from app.agents.refund.agent import RefundAgent
from app.i18n.language import language_service


def test_detect_spanish():
    lang, conf = language_service.detect("Hola, ¿dónde está mi pedido?")
    assert lang == "es"
    assert conf > 0.5


def test_detect_english():
    lang, _ = language_service.detect("Where is my order ORD-1001?")
    assert lang == "en"


@pytest.mark.asyncio
async def test_refund_eligible():
    agent = RefundAgent()
    result = await agent.run({"user_message": "I want a refund for ORD-1002"})
    assert result.data.get("order_id") == "ORD-1002"
    assert "eligible" in result.data


@pytest.mark.asyncio
async def test_to_english_passthrough():
    result = await language_service.to_english("Need help with my order")
    assert result.language == "en"
    assert "order" in result.translated_text.lower()
