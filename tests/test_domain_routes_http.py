from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.deps import get_db, require_api_key
from src.api.server import create_app
from src.config.env import get_settings
from src.core.errors import NotFoundError, ValidationError


@pytest.fixture(autouse=True)
def clear_settings_cache() -> AsyncIterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _build_app(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("OBRABOT_API_KEY", "test-api-key")
    app = create_app()

    async def _fake_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    async def _noop_api_key() -> None:
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[require_api_key] = _noop_api_key
    return app


def _client(app: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Obrabot-API-Key": "test-api-key"},
    )


async def test_rdo_rascunho_not_found_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routes import documentos as documentos_route

    app = _build_app(monkeypatch)
    monkeypatch.setattr(
        documentos_route.rdo_service,
        "create_rdo_draft",
        AsyncMock(side_effect=NotFoundError("Obra X não encontrada")),
    )

    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/rdo/rascunho",
            json={"obra_id": "X", "data_ref": "2026-06-27", "conteudo": {}},
        )

    assert resp.status_code == 404
    assert "Obra X" in resp.json()["detail"]


async def test_baseline_validar_not_found_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routes import orcamento as orcamento_route

    app = _build_app(monkeypatch)
    monkeypatch.setattr(
        orcamento_route.orcamento_service,
        "validate_baseline",
        AsyncMock(side_effect=NotFoundError("Obra Y não encontrada")),
    )

    async with _client(app) as client:
        resp = await client.post("/api/v1/baseline/validar", json={"obra_id": "Y"})

    assert resp.status_code == 404


async def test_medicoes_validation_error_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.routes import medicoes as medicoes_route

    app = _build_app(monkeypatch)
    monkeypatch.setattr(
        medicoes_route.medicao_service,
        "registrar_medicao",
        AsyncMock(side_effect=ValidationError("periodo_ref inválido")),
    )

    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/medicoes",
            json={"obra_id": "OBRA-1", "periodo_ref": "2026-AB", "itens": []},
        )

    assert resp.status_code == 400
    assert "periodo_ref" in resp.json()["detail"]


async def test_rdo_aprovar_finalizar_approval_error_returns_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api.routes import documentos as documentos_route
    from src.core.errors import ApprovalRequiredError

    app = _build_app(monkeypatch)
    monkeypatch.setattr(
        documentos_route.rdo_service,
        "approve_and_finalize_rdo",
        AsyncMock(side_effect=ApprovalRequiredError("precisa aprovação")),
    )

    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/rdo/aprovar-finalizar",
            json={"documento_id": "00000000-0000-0000-0000-000000000001", "aprovador": "eng"},
        )

    assert resp.status_code == 400
