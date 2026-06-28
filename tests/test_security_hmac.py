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


def _settings(secret: str = SECRET) -> SimpleNamespace:
    return SimpleNamespace(openclaw_shared_secret=secret)


def _make_request(body: bytes, method: str = "POST", path: str = PATH) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
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


async def test_valid_signature_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", _settings)
    event_id = "evt-1"
    body = json.dumps({"event_id": event_id, "obra_id": "OBRA-001"}).encode()
    ts = _now()
    sig = _sign(SECRET, ts, event_id, body)
    request = _make_request(body)
    # Não deve levantar exceção.
    await security.verify_hmac_signature(sig, ts, event_id, request=request)


async def test_invalid_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", _settings)
    event_id = "evt-1"
    body = json.dumps({"event_id": event_id}).encode()
    ts = _now()
    request = _make_request(body)
    with pytest.raises(HTTPException) as exc:
        await security.verify_hmac_signature("deadbeef", ts, event_id, request=request)
    assert exc.value.status_code == 401


async def test_expired_timestamp_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", _settings)
    event_id = "evt-1"
    body = json.dumps({"event_id": event_id}).encode()
    old = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig = _sign(SECRET, old, event_id, body)
    request = _make_request(body)
    with pytest.raises(HTTPException) as exc:
        await security.verify_hmac_signature(sig, old, event_id, request=request)
    assert exc.value.status_code == 401


async def test_missing_header_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", _settings)
    body = json.dumps({"event_id": "evt-1"}).encode()
    request = _make_request(body)
    with pytest.raises(HTTPException) as exc:
        await security.verify_hmac_signature(None, _now(), None, request=request)
    assert exc.value.status_code == 401


async def test_event_id_mismatch_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", _settings)
    body = json.dumps({"event_id": "evt-payload"}).encode()
    ts = _now()
    # Assina com o event_id do header (assinatura válida), mas header != payload.
    sig = _sign(SECRET, ts, "evt-header", body)
    request = _make_request(body)
    with pytest.raises(HTTPException) as exc:
        await security.verify_hmac_signature(sig, ts, "evt-header", request=request)
    assert exc.value.status_code == 401


async def test_no_secret_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: _settings(""))
    request = _make_request(b"{}")
    # Sem segredo configurado, a verificação é ignorada (dev).
    await security.verify_hmac_signature(None, None, None, request=request)
