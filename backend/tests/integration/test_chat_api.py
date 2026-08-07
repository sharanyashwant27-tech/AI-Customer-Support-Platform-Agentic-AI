"""Chat API integration tests."""


def test_chat_message(client):
    response = client.post(
        "/api/v1/chat/message",
        json={"message": "What is your return policy?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reply"]
    assert data["session_id"]
    assert data["intent"] == "knowledge"
    assert "master" in data["agents_used"]


def test_chat_escalation(client):
    response = client.post(
        "/api/v1/chat/message",
        json={"message": "Please connect me to a human representative"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "escalation"
    assert data["handoff_required"] is True


def test_order_lookup(client):
    response = client.post(
        "/api/v1/orders/lookup",
        json={"order_id": "ORD-1001"},
    )
    assert response.status_code == 200
    assert response.json()["order_id"] == "ORD-1001"


def test_create_ticket(client):
    response = client.post(
        "/api/v1/tickets",
        json={"subject": "Broken item", "description": "Arrived damaged"},
    )
    assert response.status_code == 201
    assert response.json()["ticket_number"].startswith("TKT-")
