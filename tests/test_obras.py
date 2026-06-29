from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.api.routes import obras as obras_route
from src.schemas.obras import ObraCreate


def test_obra_create_normalizes_id_and_strips_text() -> None:
    payload = ObraCreate(id=" obra-001 ", nome=" Obra Inicial ", status=" ativa ")

    assert payload.id == "OBRA-001"
    assert payload.nome == "Obra Inicial"
    assert payload.status == "ativa"


def test_obra_create_rejects_invalid_id() -> None:
    with pytest.raises(ValidationError):
        ObraCreate(id="obra 001", nome="Obra Inicial")


async def test_criar_obra_returns_typed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    obra = SimpleNamespace(
        id="OBRA-001",
        nome="Obra Inicial",
        slug="obra-inicial",
        status="ativa",
        metadata_json=None,
        created_at=None,
        updated_at=None,
    )
    session = AsyncMock()
    monkeypatch.setattr(obras_route.obra_service, "upsert_obra", AsyncMock(return_value=obra))

    response = await obras_route.criar_obra(
        ObraCreate(id="obra-001", nome="Obra Inicial"), session
    )

    assert response.id == "OBRA-001"
    assert response.nome == "Obra Inicial"
    session.commit.assert_awaited_once()
