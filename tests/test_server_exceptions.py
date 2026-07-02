from __future__ import annotations

import httpx
import pytest

from src.api.server import create_app


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("ADMIN_PASSWORD", "segredo123")
    monkeypatch.setenv("SESSION_SECRET", "session-secret-xyz")


async def test_unhandled_exception_returns_opaque_500() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Erro interno do servidor"
    assert "secret" not in response.text
