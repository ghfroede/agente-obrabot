from __future__ import annotations

import pytest

from src.api.server import create_app
from src.config.env import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_valid_prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.setenv("CORS_ORIGIN", "https://admin.example.com")
    monkeypatch.setenv("OBRABOT_API_KEY", "prod-api-key-for-ci-123456")
    monkeypatch.setenv("OPENCLAW_SHARED_SECRET", "prod-openclaw-hmac-for-ci-123456")
    monkeypatch.setenv("SESSION_SECRET", "prod-session-secret-for-ci-123456")
    monkeypatch.setenv("ADMIN_PASSWORD", "prod-admin-password-for-ci-123456")


@pytest.mark.parametrize(
    ("env_name", "value"),
    [
        ("OBRABOT_API_KEY", "change-me-in-production"),
        ("OPENCLAW_SHARED_SECRET", "change-me-in-production"),
        ("SESSION_SECRET", "secret"),
        ("ADMIN_PASSWORD", "password"),
        ("OPENAI_API_KEY", "sk-your-key-here"),
    ],
)
def test_create_app_rejects_placeholder_secret_in_production(
    monkeypatch: pytest.MonkeyPatch, env_name: str, value: str
) -> None:
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv(env_name, value)

    with pytest.raises(RuntimeError, match=env_name):
        create_app()


@pytest.mark.parametrize("env_name", ["OBRABOT_API_KEY", "OPENCLAW_SHARED_SECRET"])
def test_create_app_requires_mandatory_secrets_in_production(
    monkeypatch: pytest.MonkeyPatch, env_name: str
) -> None:
    _set_valid_prod_env(monkeypatch)
    monkeypatch.delenv(env_name)

    with pytest.raises(RuntimeError, match=env_name):
        create_app()
