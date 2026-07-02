from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from rq import Retry

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
    session.add = MagicMock()
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
    assert entrada.data_ref is None
    assert entrada.metadata_json is None
    assert entrada.hash_sha256 == content_hash("api", "OBRA-001", "executamos alvenaria")
    session.add.assert_called_once()
    session.flush.assert_awaited_once()


async def test_ingest_telegram_duplicate_returns_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    obra = SimpleNamespace(id="OBRA-001", nome="Obra 1")

    cached = {"status": "queued", "entrada_id": "e-1", "event_id": "evt-1"}

    async def fake_claim(_session: object, **_kwargs: object) -> object:
        return SimpleNamespace(status="completed", response_json=cached)

    monkeypatch.setattr(entrada_service.ingestao_service, "claim_idempotency", fake_claim)

    payload = OpenClawTelegramPayload(
        event_id="evt-1",
        obra_id="OBRA-001",
        telegram=TelegramEvent(message_id=1, chat=TelegramChat(id=10), text="oi"),
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.get = AsyncMock(return_value=obra)

    result = await entrada_service.ingest_telegram(session, payload)

    assert result == cached
    # Caminho duplicado não deve persistir nada.
    session.add.assert_not_called()


async def test_ingest_telegram_without_obra_creates_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        entrada_service.ingestao_service,
        "claim_idempotency",
        AsyncMock(return_value=None),
    )
    complete = AsyncMock()
    monkeypatch.setattr(entrada_service.ingestao_service, "complete_idempotency", complete)
    monkeypatch.setattr(
        entrada_service.obra_service,
        "active_obras_summary",
        AsyncMock(return_value=[{"id": "OBRA-001", "nome": "Obra 1", "status": "ativa"}]),
    )
    enqueue = MagicMock()
    monkeypatch.setattr(entrada_service, "enqueue_entrada", enqueue)

    payload = OpenClawTelegramPayload(
        event_id="evt-sem-obra",
        telegram=TelegramEvent(
            message_id=1,
            chat=TelegramChat(id=10, type="group"),
            text="sem obra",
            date=1782529200,
            photo=[{"file_id": "P1", "file_size": 100}],
        ),
    )
    session = AsyncMock()
    session.add = MagicMock()
    no_context = MagicMock()
    no_context.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=no_context)

    result = await entrada_service.ingest_telegram(session, payload)

    assert result["status"] == entrada_service.PENDING_OBRA_STATUS
    assert result["obra_id"] is None
    assert result["obras_disponiveis"][0]["id"] == "OBRA-001"
    assert "OBRA-001" in result["mensagem"]
    assert session.add.call_count == 2
    assert session.add.call_args_list[0].args[0].obra_id is None
    assert session.add.call_args_list[1].args[0].obra_id is None
    assert session.add.call_args_list[1].args[0].status == entrada_service.PENDING_OBRA_STATUS
    assert session.add.call_args_list[1].args[0].data_ref == date(2026, 6, 27)
    metadata = session.add.call_args_list[1].args[0].metadata_json
    assert metadata["chat_id"] == 10
    assert metadata["chat_type"] == "group"
    assert metadata["media_count"] == 1
    assert metadata["media"][0]["kind"] == "foto"
    enqueue.assert_not_called()
    complete.assert_awaited_once()


async def test_ingest_telegram_uses_obra_prefix_and_enqueues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obra = SimpleNamespace(id="OBRA-001")
    monkeypatch.setattr(
        entrada_service.ingestao_service,
        "claim_idempotency",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        entrada_service.ingestao_service,
        "complete_idempotency",
        AsyncMock(),
    )

    async def fake_to_thread(func: object, *args: object) -> None:
        assert func == entrada_service.enqueue_entrada
        assert len(args) == 1

    monkeypatch.setattr(entrada_service.asyncio, "to_thread", fake_to_thread)

    payload = OpenClawTelegramPayload(
        event_id="evt-prefixo",
        telegram=TelegramEvent(
            message_id=1,
            chat=TelegramChat(id=10, type="group"),
            text="OBRA-001: concretagem concluída",
        ),
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.get = AsyncMock(return_value=obra)

    result = await entrada_service.ingest_telegram(session, payload)

    assert result["status"] == "queued"
    assert result["obra_id"] == "OBRA-001"
    assert result["obra_resolution_source"] == "prefixo"
    entrada = session.add.call_args_list[1].args[0]
    assert entrada.obra_id == "OBRA-001"
    assert entrada.metadata_json["obra_resolution_source"] == "prefixo"


async def test_ingest_telegram_unknown_obra_creates_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        entrada_service.ingestao_service,
        "claim_idempotency",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        entrada_service.ingestao_service,
        "complete_idempotency",
        AsyncMock(),
    )
    monkeypatch.setattr(
        entrada_service.obra_service,
        "active_obras_summary",
        AsyncMock(return_value=[]),
    )

    payload = OpenClawTelegramPayload(
        event_id="evt-obra-invalida",
        obra_id="OBRA-X",
        telegram=TelegramEvent(message_id=1, chat=TelegramChat(id=10), text="oi"),
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.get = AsyncMock(return_value=None)

    result = await entrada_service.ingest_telegram(session, payload)

    assert result["status"] == entrada_service.PENDING_OBRA_STATUS
    assert result["obra_id_solicitado"] == "OBRA-X"
    assert "não está cadastrada" in result["mensagem"]


async def test_resolve_pending_obra_links_and_enqueues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entrada_id = uuid4()
    entrada = SimpleNamespace(
        id=entrada_id,
        status=entrada_service.PENDING_OBRA_STATUS,
        obra_id=None,
        raw_payload={"event_id": "evt-1"},
        metadata_json={},
        event_id="evt-1",
    )
    obra = SimpleNamespace(id="OBRA-001")
    msg = SimpleNamespace(obra_id=None, raw_payload={"event_id": "evt-1"})
    scalar = MagicMock()
    scalar.scalar_one_or_none.return_value = msg
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[entrada, obra])
    session.execute = AsyncMock(return_value=scalar)

    async def fake_to_thread(func: object, *args: object) -> None:
        assert func == entrada_service.enqueue_entrada
        assert args == (str(entrada_id),)

    monkeypatch.setattr(entrada_service.asyncio, "to_thread", fake_to_thread)

    result = await entrada_service.resolve_pending_obra(
        session, entrada_id=entrada_id, obra_id="obra-001"
    )

    assert result["status"] == "queued"
    assert entrada.obra_id == "OBRA-001"
    assert entrada.status == "received"
    assert entrada.raw_payload["obra_id"] == "OBRA-001"
    assert entrada.metadata_json["obra_resolvida_id"] == "OBRA-001"
    assert msg.obra_id == "OBRA-001"
    assert msg.raw_payload["obra_id"] == "OBRA-001"
    session.commit.assert_awaited_once()


def test_enqueue_entrada_uses_configured_timeout_and_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeQueue:
        def __init__(self, name: str, connection: object) -> None:
            captured["queue_name"] = name
            captured["connection"] = connection

        def enqueue(self, *args: object, **kwargs: object) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(entrada_service, "get_redis", lambda: "redis-conn")
    monkeypatch.setattr(entrada_service, "Queue", FakeQueue)
    monkeypatch.setattr(
        entrada_service,
        "get_settings",
        lambda: SimpleNamespace(
            redis_url="redis://localhost:6379/0",
            rq_job_timeout_seconds=123,
            rq_retry_max=3,
            rq_retry_intervals=[30, 120, 300],
        ),
    )

    entrada_service.enqueue_entrada("entrada-1")

    assert captured["queue_name"] == "obrabot"
    assert captured["connection"] == "redis-conn"
    assert captured["args"] == ("src.worker.jobs.process_entrada", "entrada-1")
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["job_timeout"] == 123
    retry = kwargs["retry"]
    assert isinstance(retry, Retry)
    assert retry.max == 3
    assert retry.intervals == [30, 120, 300]
