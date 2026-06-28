from fastapi.testclient import TestClient

from src.api.server import create_app


def test_health_endpoint_structure():
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code in (200, 503)
    body = response.json()
    assert "status" in body
    assert "checks" in body
    assert body["checks"]["app"] == "ok"
