from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.core import security
from src.core.errors import ForbiddenError
from src.schemas.domain import OpenClawTelegramPayload, TelegramChat, TelegramEvent, TelegramUser

SECRET = "prod-secret"
PATH = "/api/v1/openclaw/telegram-event"


def _settings_production(secret: str = "", **overrides: object) -> SimpleNamespace:
    base = {
        "openclaw_shared_secret": secret,
        "is_production": True,
        "openclaw_require_hmac": True,
        "openclaw_max_clock_skew_seconds": 300,
        "webhook_max_body_bytes": 10_485_760,
        "rate_limit_enabled": False,
        "allowed_chat_ids": frozenset(),
        "allowed_user_ids": frozenset(),
        "allowed_thread_ids": frozenset(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_request(body: bytes = b"{}", headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": PATH,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": b"",
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


async def test_secret_empty_fails_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings_production(""))
    request = _make_request()
    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(request)
    assert exc.value.status_code == 500
    assert "OPENCLAW_SHARED_SECRET" in exc.value.detail


async def test_secret_empty_fails_when_hmac_required_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            openclaw_shared_secret="",
            is_production=False,
            openclaw_require_hmac=True,
            openclaw_max_clock_skew_seconds=300,
            webhook_max_body_bytes=10_485_760,
            rate_limit_enabled=False,
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(_make_request())
    assert exc.value.status_code == 500
    assert "OPENCLAW_SHARED_SECRET" in exc.value.detail


async def test_secret_empty_allowed_in_development_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            openclaw_shared_secret="",
            is_production=False,
            openclaw_require_hmac=False,
            openclaw_max_clock_skew_seconds=300,
            webhook_max_body_bytes=10_485_760,
            rate_limit_enabled=False,
        ),
    )
    with caplog.at_level(logging.WARNING):
        body = await security.verify_openclaw_webhook(_make_request())
    assert body == b"{}"
    assert any("OPENCLAW_SHARED_SECRET vazio" in r.message for r in caplog.records)


def test_unauthorized_chat_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            allowed_chat_ids=frozenset({"100"}),
            allowed_user_ids=frozenset(),
            allowed_thread_ids=frozenset(),
        ),
    )
    payload = OpenClawTelegramPayload(
        event_id="e1",
        obra_id="OBRA-001",
        telegram=TelegramEvent(
            message_id=1,
            chat=TelegramChat(id=999, type="group"),
            text="oi",
        ),
    )
    with pytest.raises(ForbiddenError):
        security.validate_telegram_allowlist(payload)


def test_unauthorized_user_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            allowed_chat_ids=frozenset(),
            allowed_user_ids=frozenset({"42"}),
            allowed_thread_ids=frozenset(),
        ),
    )
    payload = OpenClawTelegramPayload(
        event_id="e1",
        obra_id="OBRA-001",
        telegram=TelegramEvent(
            message_id=1,
            chat=TelegramChat(id=100, type="private"),
            from_user=TelegramUser(id=7),
            text="oi",
        ),
    )
    with pytest.raises(ForbiddenError):
        security.validate_telegram_allowlist(payload)


def test_allowed_chat_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            allowed_chat_ids=frozenset({"100"}),
            allowed_user_ids=frozenset(),
            allowed_thread_ids=frozenset(),
        ),
    )
    payload = OpenClawTelegramPayload(
        event_id="e1",
        obra_id="OBRA-001",
        telegram=TelegramEvent(
            message_id=1,
            chat=TelegramChat(id=100, type="group"),
            text="oi",
        ),
    )
    security.validate_telegram_allowlist(payload)


async def test_body_too_large_returns_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            openclaw_shared_secret=SECRET,
            is_production=False,
            openclaw_require_hmac=False,
            openclaw_max_clock_skew_seconds=300,
            webhook_max_body_bytes=10,
            rate_limit_enabled=False,
        ),
    )
    big = b"x" * 20
    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(_make_request(big))
    assert exc.value.status_code == 413


async def test_static_secret_header_rejected_when_hmac_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            openclaw_shared_secret=SECRET,
            is_production=True,
            openclaw_require_hmac=True,
            openclaw_max_clock_skew_seconds=300,
            webhook_max_body_bytes=10_485_760,
            rate_limit_enabled=False,
        ),
    )
    body = json.dumps({"event_id": "e1"}).encode()
    request = _make_request(body, headers={"X-OpenClaw-Secret": SECRET})

    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(request)
    assert exc.value.status_code == 401


async def test_static_secret_header_accepted_in_legacy_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            openclaw_shared_secret=SECRET,
            is_production=False,
            openclaw_require_hmac=False,
            openclaw_max_clock_skew_seconds=300,
            webhook_max_body_bytes=10_485_760,
            rate_limit_enabled=False,
        ),
    )
    body = json.dumps({"event_id": "e1"}).encode()
    request = _make_request(body, headers={"X-OpenClaw-Secret": SECRET})
    result = await security.verify_openclaw_webhook(request)
    assert result == body
