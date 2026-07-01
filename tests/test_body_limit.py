from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.api.middleware import BodySizeLimitMiddleware
from src.api.routes import admin as admin_route
from src.api.server import create_app
from src.config.env import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> AsyncIterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client(app: ASGIApp) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _configure_admin(monkeypatch: pytest.MonkeyPatch, *, body_limit: int = 128) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("ADMIN_PASSWORD", "segredo123")
    monkeypatch.setenv("SESSION_SECRET", "session-secret-xyz")
    monkeypatch.setenv("ADMIN_LOGIN_MAX_BODY_BYTES", str(body_limit))
    monkeypatch.setattr(admin_route.rate_limit_service, "check_admin_login_limit", lambda **_: None)


async def test_admin_login_rejects_payload_above_route_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_admin(monkeypatch, body_limit=32)
    app = create_app()

    async with _client(app) as client:
        response = await client.post(
            "/admin/login",
            data={"senha": "x" * 64},
            follow_redirects=False,
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Payload excede limite de tamanho"


async def test_admin_login_accepts_payload_below_route_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_admin(monkeypatch, body_limit=128)
    app = create_app()

    async with _client(app) as client:
        response = await client.post(
            "/admin/login",
            data={"senha": "segredo123"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


async def test_protected_json_route_rejects_payload_above_default_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBRABOT_API_KEY", "test-secret")
    monkeypatch.setenv("API_MAX_BODY_BYTES", "64")
    app = create_app()

    async with _client(app) as client:
        response = await client.post(
            "/api/v1/triagem/classificar",
            headers={"X-Obrabot-API-Key": "test-secret"},
            json={"texto": "x" * 128},
        )

    assert response.status_code == 413


async def test_protected_json_route_accepts_payload_below_default_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBRABOT_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("API_MAX_BODY_BYTES", "1024")
    app = create_app()

    async with _client(app) as client:
        response = await client.post(
            "/api/v1/triagem/classificar",
            headers={"X-Obrabot-API-Key": "test-secret"},
            json={"texto": "Gerar RDO de hoje"},
        )

    assert response.status_code == 200
    assert response.json()["tipo_documento"] == "rdo"


async def test_openclaw_route_uses_webhook_body_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "")
    monkeypatch.setenv("OPENCLAW_REQUIRE_HMAC", "false")
    monkeypatch.setenv("WEBHOOK_MAX_BODY_BYTES", "32")
    app = create_app()

    async with _client(app) as client:
        response = await client.post(
            "/api/v1/openclaw/telegram-event",
            content=b"x" * 64,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413


async def test_openclaw_route_accepts_payload_below_webhook_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "")
    monkeypatch.setenv("OPENCLAW_REQUIRE_HMAC", "false")
    monkeypatch.setenv("WEBHOOK_MAX_BODY_BYTES", "64")
    app = create_app()

    async with _client(app) as client:
        response = await client.post("/api/v1/openclaw/telegram-event", json={})

    assert response.status_code == 422


async def test_middleware_counts_streamed_body_without_content_length() -> None:
    async def drain_app(_scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = BodySizeLimitMiddleware(
        drain_app,
        default_limit_bytes=8,
        admin_login_limit_bytes=8,
        webhook_limit_bytes=8,
    )
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/triagem/classificar",
        "headers": [],
        "query_string": b"",
    }
    inbound: list[Message] = [
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"5678", "more_body": True},
        {"type": "http.request", "body": b"9", "more_body": False},
    ]
    sent: list[Message] = []

    async def receive() -> Message:
        return inbound.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(scope, receive, send)

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 413
    assert _response_body(sent) == b'{"detail":"Payload excede limite de tamanho"}'


def _response_body(messages: list[Message]) -> bytes:
    chunks = [message.get("body", b"") for message in messages]
    return b"".join(chunk for chunk in chunks if isinstance(chunk, bytes))
