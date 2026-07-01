from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from starlette.types import ASGIApp

from src.api.routes import admin as admin_route
from src.api.server import create_app
from src.config.env import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> AsyncIterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client(app: ASGIApp, *, base_url: str = "http://test") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url=base_url)


def _configure_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("ADMIN_PASSWORD", "segredo123")
    monkeypatch.setenv("SESSION_SECRET", "session-secret-xyz")
    monkeypatch.setattr(admin_route.rate_limit_service, "check_admin_login_limit", lambda **_: None)


def _assert_base_security_headers(headers: httpx.Headers) -> None:
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert "object-src 'none'" in headers["content-security-policy"]
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert "form-action 'self'" in headers["content-security-policy"]


async def test_health_response_has_security_headers_in_development() -> None:
    app = create_app()

    async with _client(app) as client:
        response = await client.get("/health")

    assert response.status_code in (200, 503)
    _assert_base_security_headers(response.headers)
    assert "strict-transport-security" not in response.headers


async def test_admin_login_csp_allows_current_inline_admin_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_admin(monkeypatch)
    app = create_app()

    async with _client(app) as client:
        response = await client.get("/admin/login")

    assert response.status_code == 200
    _assert_base_security_headers(response.headers)
    csp = response.headers["content-security-policy"]
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data:" in csp


async def test_protected_json_route_has_security_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBRABOT_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    app = create_app()

    async with _client(app) as client:
        response = await client.post(
            "/api/v1/triagem/classificar",
            headers={"X-Obrabot-API-Key": "test-secret"},
            json={"texto": "Gerar RDO de hoje"},
        )

    assert response.status_code == 200
    _assert_base_security_headers(response.headers)


async def test_hsts_is_only_emitted_for_production_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.setenv("CORS_ORIGIN", "https://admin.example.com")
    monkeypatch.setenv("OBRABOT_API_KEY", "prod-api-key-for-ci-123456")
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "prod-openclaw-hmac-for-ci-123456")
    monkeypatch.setenv("SESSION_SECRET", "prod-session-secret-for-ci-123456")
    monkeypatch.setenv("ADMIN_PASSWORD", "prod-admin-password-for-ci-123456")
    app = create_app()

    async with _client(app, base_url="http://test") as client:
        http_response = await client.get("/health")
    async with _client(app, base_url="https://test") as client:
        https_response = await client.get("/health")

    assert "strict-transport-security" not in http_response.headers
    assert (
        https_response.headers["strict-transport-security"]
        == "max-age=31536000; includeSubDomains"
    )


async def test_hsts_honors_forwarded_proto_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.setenv("CORS_ORIGIN", "https://admin.example.com")
    monkeypatch.setenv("OBRABOT_API_KEY", "prod-api-key-for-ci-123456")
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "prod-openclaw-hmac-for-ci-123456")
    monkeypatch.setenv("SESSION_SECRET", "prod-session-secret-for-ci-123456")
    monkeypatch.setenv("ADMIN_PASSWORD", "prod-admin-password-for-ci-123456")
    app = create_app()

    async with _client(app) as client:
        response = await client.get("/health", headers={"X-Forwarded-Proto": "https"})

    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
