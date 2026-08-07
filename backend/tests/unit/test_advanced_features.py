"""Unit tests for advanced platform features."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.advanced.features import (
    auto_priority,
    detect_refund_fraud,
    list_languages,
    predict_csat,
    publish_realtime,
    record_sentiment_event,
    register_sla,
    sentiment_dashboard,
    sla_status,
    summarize_ticket,
)
from app.agents.ticket.agent import TicketManagementAgent
from app.main import app


def test_auto_priority_p1_for_urgent_refund():
    result = auto_priority(
        intent="refund",
        sentiment="angry",
        message="I want a chargeback immediately",
    )
    assert result["priority"] == "P1"
    assert result["db_priority"] == "urgent"


def test_auto_priority_p3_for_calm_product_question():
    result = auto_priority(
        intent="product",
        sentiment="happy",
        message="Where can I find the user guide?",
    )
    assert result["priority"] == "P3"


def test_refund_fraud_flags_chargeback_language():
    result = detect_refund_fraud(
        message="I will dispute with bank and demand chargeback",
        order_age_days=10,
        prior_refunds=0,
    )
    assert result["risk"] in {"medium", "high"}
    assert result["recommend_manual_review"] is True


def test_languages_catalog_has_fifty_plus():
    catalog = list_languages()
    assert catalog["count"] >= 50


def test_sla_register_and_status():
    register_sla("TKT-TEST01", priority="P1")
    items = sla_status("TKT-TEST01")
    assert len(items) == 1
    assert items[0]["priority"] == "P1"
    assert items[0]["sla_minutes"] == 60


def test_sentiment_dashboard_counts():
    record_sentiment_event(session_id="s-adv", sentiment="angry", intent="refund")
    dash = sentiment_dashboard(hours=24)
    assert dash["total"] >= 1
    assert "angry" in dash["distribution"]


def test_csat_prediction_bounds():
    pred = predict_csat(sentiment="happy", handoff=False, resolved=True)
    assert 1.0 <= pred["predicted_csat"] <= 5.0


def test_realtime_notifications():
    published = publish_realtime("test.event", {"ok": True}, channel="support")
    assert published["event"] == "test.event"
    assert "ts" in published


@pytest.mark.asyncio
async def test_ticket_agent_assigns_p_priority_and_summary():
    agent = TicketManagementAgent()
    result = await agent.run(
        {
            "user_message": "My package is delayed and I am furious — lawsuit!",
            "intent": "package_delay",
            "sentiment": "angry",
            "session_id": "t1",
        }
    )
    draft = result.data["ticket_draft"]
    assert draft["priority"] in {"P1", "P2", "P3"}
    assert draft["summary"]
    assert result.data["ai_summary"]["summary"]


@pytest.mark.asyncio
async def test_summarize_ticket_stub():
    summary = await summarize_ticket(
        subject="Payment failed",
        description="Card declined twice",
        intent="billing",
        sentiment="frustrated",
    )
    assert "summary" in summary
    assert summary["summary"]


@pytest.mark.asyncio
async def test_advanced_api_list_and_languages():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/advanced")
        assert r.status_code == 200
        assert len(r.json()["features"]) >= 16

        html = await client.get(
            "/api/v1/advanced", headers={"Accept": "text/html"}
        )
        assert html.status_code == 200
        assert "text/html" in html.headers["content-type"]
        assert b"Advanced Features" in html.content

        langs = await client.get("/api/v1/advanced/languages")
        assert langs.status_code == 200
        assert langs.json()["count"] >= 50

        pri = await client.post(
            "/api/v1/advanced/priority",
            json={"intent": "billing", "sentiment": "urgent", "message": "asap"},
        )
        assert pri.status_code == 200
        assert pri.json()["priority"] in {"P1", "P2", "P3"}
