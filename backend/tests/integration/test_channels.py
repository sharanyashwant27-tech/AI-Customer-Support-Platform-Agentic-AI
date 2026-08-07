"""Channel API smoke tests."""


def test_list_channels(client):
    response = client.get("/api/v1/channels")
    assert response.status_code == 200
    data = response.json()
    assert "whatsapp" in data["channels"]
    assert "voice" in data["channels"]
    assert "slack" in data["channels"]
    assert "teams" in data["channels"]


def test_spanish_channel_message(client):
    response = client.post(
        "/api/v1/channels/web/message",
        json={"text": "Necesito un reembolso para ORD-1001", "language": "es"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "refund"
    assert data["language"] == "es"
    assert data["text"]


def test_whatsapp_verify(client):
    response = client.get(
        "/api/v1/channels/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "aics-whatsapp-verify",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.json() == 12345
