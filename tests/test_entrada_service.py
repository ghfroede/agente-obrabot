from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.schemas.domain import OpenClawTelegramPayload, TelegramChat, TelegramEvent
from src.services import entrada_service
from src.services.entrada_service import content_hash, create_entrada_bruta


def test_content_hash_deterministic() -> None:
    a = content_hash("openclaw", "OBRA-001", "alvenaria")
    b = content_hash("openclaw", "OBRA-001", "alvenaria")
    c = content_hash("api", "OBRA-001", "alvenaria")
    assert a == b
    assert a != c
    assert len(a) == 64


async def test_create_entrada_bruta_defaults_received() -> None:
    session = AsyncMock()
    entrada = await create_entrada_bruta(
        session,
        source="api",
        obra_id="OBRA-001",
        text="executamos alvenaria",
        channel="api",
        author="eng",
    )

    assert entrada.source == "api"
    assert entrada.status == "received"
    assert entrada.obra_id == "OBRA-001"
    assert entrada.hash_sha256 == content_hash("api", "OBRA-001", "executamos alvenaria")
    session.add.assert_called_once()
    session.flush.assert_awaited_once()


async def test_ingest_telegram_duplicate_returns_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    obra = SimpleNamespace(id="OBRA-001", nome="Obra 1")

    async def fake_ensure_obra(_session: object, _obra_id: str, _nome: str | None = None) -> object:
        return obra

    cached = {"status": "queued", "entrada_id": "e-1", "event_id": "evt-1"}

    async def fake_claim(_session: object, **_kwargs: object) -> object:
        return SimpleNamespace(status="completed", response_json=cached)

    monkeypatch.setattr(entrada_service.ingestao_service, "ensure_obra", fake_ensure_obra)
    monkeypatch.setattr(entrada_service.ingestao_service, "claim_idempotency", fake_claim)

    payload = OpenClawTelegramPayload(
        event_id="evt-1",
        obra_id="OBRA-001",
        telegram=TelegramEvent(message_id=1, chat=TelegramChat(id=10), text="oi"),
    )
    session = AsyncMock()

    result = await entrada_service.ingest_telegram(session, payload)

    assert result == cached
    # Caminho duplicado não deve persistir nada.
    session.add.assert_not_called()
