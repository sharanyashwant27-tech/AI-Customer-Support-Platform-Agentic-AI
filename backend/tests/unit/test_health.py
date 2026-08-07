"""Health endpoint tests."""


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert data["port"] == "8917"


def test_root_format_json_browser(client):
    response = client.get("/?format=json", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"API Root JSON" in response.content
    assert b"AI Customer Support Platform" in response.content


def test_root_format_raw_json(client):
    response = client.get("/?format=raw", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.json()["port"] == "8917"


def test_root_html_for_browsers(client):
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # SPA when frontend/dist exists; otherwise API console landing
    body = response.content
    assert b"AICS" in body or b"Customer Support" in body or b"Customer Chat UI" in body or b"OpenAPI Docs" in body


def test_console_page(client):
    response = client.get("/console")
    assert response.status_code == 200
    assert b"OpenAPI Docs" in response.content or b"Customer Chat UI" in response.content


def test_api_indexes(client):
    assert client.get("/api").status_code == 200
    assert client.get("/api/v1").status_code == 200
    assert client.get("/favicon.ico").status_code == 200


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "services" in data


def test_health_html_for_browsers(client):
    response = client.get("/api/v1/health", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"API Health" in response.content
