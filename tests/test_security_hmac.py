from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.core import security

SECRET = "testsecret"
PATH = "/api/v1/openclaw/telegram-event"


def _settings(
    secret: str = SECRET,
    *,
    production: bool = False,
    require_hmac: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        openclaw_shared_secret=secret,
        is_production=production,
        openclaw_require_hmac=require_hmac,
        openclaw_max_clock_skew_seconds=300,
        webhook_max_body_bytes=10_485_760,
        rate_limit_enabled=False,
        allowed_chat_ids=frozenset(),
        allowed_user_ids=frozenset(),
        allowed_thread_ids=frozenset(),
    )


def _make_request(
    body: bytes,
    method: str = "POST",
    path: str = PATH,
    headers: dict[str, str] | None = None,
) -> Request:
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": hdrs,
        "query_string": b"",
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _sign(secret: str, timestamp: str, event_id: str, body: bytes, method: str = "POST") -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([timestamp, event_id, method, PATH, body_hash]).encode()
    return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _auth_headers(secret: str, event_id: str, body: bytes, ts: str | None = None) -> dict[str, str]:
    timestamp = ts or _now()
    sig = _sign(secret, timestamp, event_id, body)
    return {
        "X-OpenClaw-Signature": sig,
        "X-OpenClaw-Timestamp": timestamp,
        "X-OpenClaw-Event-Id": event_id,
    }


async def test_valid_signature_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(require_hmac=True))
    monkeypatch.setattr(security.rate_limit_service, "check_openclaw_limits", lambda **_k: None)
    event_id = "evt-1"
    body = json.dumps({"event_id": event_id, "obra_id": "OBRA-001"}).encode()
    request = _make_request(body, headers=_auth_headers(SECRET, event_id, body))
    await security.verify_openclaw_webhook(request)


async def test_invalid_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(require_hmac=True))
    event_id = "evt-1"
    body = json.dumps({"event_id": event_id}).encode()
    headers = _auth_headers(SECRET, event_id, body)
    headers["X-OpenClaw-Signature"] = "deadbeef"
    request = _make_request(body, headers=headers)
    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(request)
    assert exc.value.status_code == 401


async def test_expired_timestamp_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(require_hmac=True))
    event_id = "evt-1"
    body = json.dumps({"event_id": event_id}).encode()
    old = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    request = _make_request(body, headers=_auth_headers(SECRET, event_id, body, ts=old))
    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(request)
    assert exc.value.status_code == 401


async def test_missing_header_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(require_hmac=True))
    body = json.dumps({"event_id": "evt-1"}).encode()
    request = _make_request(body)
    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(request)
    assert exc.value.status_code == 401


async def test_event_id_mismatch_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(require_hmac=True))
    body = json.dumps({"event_id": "evt-payload"}).encode()
    ts = _now()
    headers = _auth_headers(SECRET, "evt-header", body, ts=ts)
    request = _make_request(body, headers=headers)
    with pytest.raises(HTTPException) as exc:
        await security.verify_openclaw_webhook(request)
    assert exc.value.status_code == 401


async def test_no_secret_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(""))
    request = _make_request(b"{}")
    body = await security.verify_openclaw_webhook(request)
    assert body == b"{}"


async def test_verify_hmac_signature_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(""))
    request = _make_request(b"{}")
    await security.verify_hmac_signature(request)
