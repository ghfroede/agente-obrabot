from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from src.core.errors import RateLimitError
from src.services import rate_limit_service


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds


def _settings(*, limit: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_window_seconds=60,
        rate_limit_expensive_per_minute=limit,
        rate_limit_protected_per_minute=120,
    )


def test_expensive_protected_route_rate_limit_raises_429_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit_service, "get_settings", lambda: _settings(limit=1))
    monkeypatch.setattr(rate_limit_service, "_redis", lambda: fake)

    rate_limit_service.check_protected_route_limit(
        api_key="super-secret-api-key",
        ip="203.0.113.10",
        method="POST",
        path="/api/v1/triagem/classificar",
    )

    with pytest.raises(RateLimitError):
        rate_limit_service.check_protected_route_limit(
            api_key="super-secret-api-key",
            ip="203.0.113.10",
            method="POST",
            path="/api/v1/triagem/classificar",
        )


def test_protected_route_rate_limit_logs_fingerprint_without_secret(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit_service, "get_settings", lambda: _settings(limit=1))
    monkeypatch.setattr(rate_limit_service, "_redis", lambda: fake)

    with caplog.at_level(logging.WARNING):
        rate_limit_service.check_protected_route_limit(
            api_key="super-secret-api-key",
            ip="203.0.113.10",
            method="POST",
            path="/api/v1/rdo/gerar",
        )
        with pytest.raises(RateLimitError):
            rate_limit_service.check_protected_route_limit(
                api_key="super-secret-api-key",
                ip="203.0.113.10",
                method="POST",
                path="/api/v1/rdo/gerar",
            )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "api_key_fp=" in messages
    assert "super-secret-api-key" not in messages
    assert "/api/v1/rdo/gerar" in messages


def test_protected_route_rate_limit_uses_lighter_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_window_seconds=60,
        rate_limit_expensive_per_minute=1,
        rate_limit_protected_per_minute=2,
    )
    monkeypatch.setattr(rate_limit_service, "get_settings", lambda: settings)
    monkeypatch.setattr(rate_limit_service, "_redis", lambda: fake)

    for _ in range(2):
        rate_limit_service.check_protected_route_limit(
            api_key="super-secret-api-key",
            ip="203.0.113.10",
            method="GET",
            path="/api/v1/obras",
        )

    with pytest.raises(RateLimitError):
        rate_limit_service.check_protected_route_limit(
            api_key="super-secret-api-key",
            ip="203.0.113.10",
            method="GET",
            path="/api/v1/obras",
        )
