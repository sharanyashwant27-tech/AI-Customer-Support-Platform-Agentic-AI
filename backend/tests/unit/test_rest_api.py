"""Public REST API contract tests."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_root_lists_rest_contract():
    client = TestClient(create_app())
    res = client.get("/")
    assert res.status_code == 200
    rest = res.json()["rest"]
    assert "POST /chat" in rest
    assert "POST /ticket" in rest
    assert "GET /ticket/{id}" in rest
    assert "GET /orders/{id}" in rest
    assert "POST /upload" in rest
    assert "POST /knowledge/index" in rest
    assert "GET /customer/{id}" in rest
    assert "POST /feedback" in rest


def test_post_chat_alias():
    client = TestClient(create_app())
    res = client.post(
        "/chat",
        json={"message": "What is your return policy?", "session_id": "rest-1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert data["session_id"] == "rest-1"


def test_get_order_alias():
    client = TestClient(create_app())
    res = client.get("/orders/ORD-1002")
    assert res.status_code == 200
    assert res.json()["order_id"] == "ORD-1002"


def test_post_knowledge_index_alias():
    client = TestClient(create_app())
    res = client.post(
        "/knowledge/index",
        json={
            "title": "Test Policy",
            "content": "Customers may contact support for billing questions anytime.",
            "knowledge_source": "policies",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] in {"indexed", "empty"}
    assert res.json()["chunks_created"] >= 0


def test_post_feedback_alias():
    client = TestClient(create_app())
    res = client.post(
        "/feedback",
        json={"rating": 5, "comment": "Great", "session_id": "rest-fb"},
    )
    assert res.status_code == 201
    assert res.json()["rating"] == 5
