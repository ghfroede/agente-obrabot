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


def _set_prod_env(monkeypatch: pytest.MonkeyPatch, *, cors_origin: str) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "prod-session-secret")
    monkeypatch.setenv("CORS_ORIGIN", cors_origin)


@pytest.mark.parametrize("cors_origin", ["", "*", "https://admin.example.com,*"])
def test_create_app_rejects_wildcard_or_empty_cors_in_production(
    monkeypatch: pytest.MonkeyPatch,
    cors_origin: str,
) -> None:
    _set_prod_env(monkeypatch, cors_origin=cors_origin)

    with pytest.raises(RuntimeError, match="CORS_ORIGIN"):
        create_app()


async def test_cors_preflight_allows_explicit_origin_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = "https://admin.example.com"
    _set_prod_env(
        monkeypatch,
        cors_origin=f"{origin},https://ops.example.com",
    )
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/triagem/classificar",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Obrabot-API-Key, Content-Type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed_methods = response.headers["access-control-allow-methods"]
    assert "GET" in allowed_methods
    assert "POST" in allowed_methods
    assert "OPTIONS" in allowed_methods
    assert "PUT" not in allowed_methods
    assert "DELETE" not in allowed_methods
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed_headers
    assert "x-obrabot-api-key" in allowed_headers
    assert "x-openclaw-signature" in allowed_headers
    assert "authorization" not in allowed_headers


async def test_cors_preflight_rejects_origin_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_prod_env(monkeypatch, cors_origin="https://admin.example.com")
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/triagem/classificar",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Obrabot-API-Key, Content-Type",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
