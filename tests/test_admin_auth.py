from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.deps import get_db
from src.api.routes import admin as admin_route
from src.api.server import create_app
from src.config.env import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> AsyncIterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app_with_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("ADMIN_PASSWORD", "segredo123")
    monkeypatch.setenv("SESSION_SECRET", "session-secret-xyz")
    monkeypatch.setattr(admin_route.rate_limit_service, "check_admin_login_limit", lambda **_: None)
    app = create_app()

    async def _fake_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    return app


def _client(app: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/admin"),
        ("GET", "/admin/entradas"),
        ("GET", "/admin/obras"),
        ("GET", "/admin/documentos/00000000-0000-0000-0000-000000000001"),
        ("POST", "/admin/obras/OBRA-1/status"),
    ],
)
async def test_guard_redirects_without_session(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    app = _app_with_db(monkeypatch)
    async with _client(app) as client:
        response = await client.request(method, path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


async def test_login_smoke_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_db(monkeypatch)
    async with _client(app) as client:
        response = await client.get("/admin/login")

    assert response.status_code == 200
    assert "Senha" in response.text


async def test_login_correct_password_sets_session(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_db(monkeypatch)
    async with _client(app) as client:
        response = await client.post(
            "/admin/login",
            data={"senha": "segredo123"},
            headers={"Origin": "http://test"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert "session" in response.cookies or any(
        "session" in c for c in response.headers.get_list("set-cookie")
    )


async def test_login_wrong_password_rerenders_200(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_db(monkeypatch)
    async with _client(app) as client:
        response = await client.post(
            "/admin/login", data={"senha": "errada"}, follow_redirects=False
        )

    assert response.status_code == 200
    assert "inválida" in response.text


async def test_login_empty_config_in_prod_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.setenv("CORS_ORIGIN", "https://admin.example.com")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("OBRABOT_API_KEY", raising=False)
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "prod-openclaw-hmac-for-ci-123456")
    monkeypatch.setenv("SESSION_SECRET", "prod-session-secret-for-ci-123456")
    monkeypatch.setattr(admin_route.rate_limit_service, "check_admin_login_limit", lambda **_: None)

    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        create_app()


async def test_create_app_fails_closed_without_session_secret_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.setenv("CORS_ORIGIN", "https://admin.example.com")
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "prod-openclaw-hmac-for-ci-123456")
    monkeypatch.setenv("ADMIN_PASSWORD", "prod-admin-password-for-ci-123456")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("OBRABOT_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OBRABOT_API_KEY"):
        create_app()


async def test_same_origin_rejects_host_prefix_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_db(monkeypatch)
    async with _client(app) as client:
        response = await client.post(
            "/admin/logout",
            headers={"Origin": "http://test.evil.com"},
            follow_redirects=False,
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Origem não autorizada"


async def test_same_origin_allows_exact_host(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_db(monkeypatch)
    async with _client(app) as client:
        await client.post(
            "/admin/login",
            data={"senha": "segredo123"},
            headers={"Origin": "http://test"},
            follow_redirects=False,
        )
        response = await client.post(
            "/admin/logout",
            headers={"Origin": "http://test"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


async def test_login_rejects_host_prefix_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_db(monkeypatch)
    async with _client(app) as client:
        response = await client.post(
            "/admin/login",
            data={"senha": "segredo123"},
            headers={"Origin": "http://test.evil.com"},
            follow_redirects=False,
        )

    assert response.status_code == 403
