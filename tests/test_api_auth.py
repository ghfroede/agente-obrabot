from __future__ import annotations

import httpx
import pytest

from src.api.server import create_app
from src.config.env import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_health_does_not_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBRABOT_API_KEY", "test-secret")
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code in (200, 503)
    assert response.status_code != 401


async def test_fastapi_docs_are_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGIN", "https://admin.example.com")
    monkeypatch.setenv("OBRABOT_API_KEY", "test-secret")
    monkeypatch.setenv("SESSION_SECRET", "prod-session-secret")
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        docs_response = await client.get("/docs")
        schema_response = await client.get("/openapi.json")

    assert docs_response.status_code == 404
    assert schema_response.status_code == 404


async def test_openclaw_webhook_does_not_require_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OBRABOT_API_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "")
    monkeypatch.setenv("OPENCLAW_REQUIRE_HMAC", "false")
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/openclaw/telegram-event", json={})

    assert response.status_code == 422


async def test_protected_route_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBRABOT_API_KEY", "test-secret")
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/triagem/classificar",
            json={"texto": "Gerar RDO de hoje"},
        )

    assert response.status_code == 401


async def test_protected_route_accepts_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBRABOT_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/triagem/classificar",
            headers={"X-Obrabot-API-Key": "test-secret"},
            json={"texto": "Gerar RDO de hoje"},
        )

    assert response.status_code == 200
    assert response.json()["tipo_documento"] == "rdo"
