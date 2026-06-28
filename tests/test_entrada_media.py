from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import entrada_service
from src.services.entrada_service import _compose_triagem_text, _primary_arquivo_id


def test_compose_triagem_text_merges_media() -> None:
    midias = [
        {"kind": "foto", "descricao": "parede pronta"},
        {"kind": "audio", "transcricao": "concretagem ok"},
    ]
    text = _compose_triagem_text("texto base", midias)
    assert "texto base" in text
    assert "[Foto] parede pronta" in text
    assert "[Áudio] concretagem ok" in text


def test_compose_triagem_text_fallback_when_empty() -> None:
    assert _compose_triagem_text(None, []) == "[mensagem sem texto — mídia]"


def test_primary_arquivo_id_picks_first() -> None:
    aid = str(uuid.uuid4())
    midias = [{"kind": "foto", "erro": "x"}, {"kind": "foto", "arquivo_id": aid}]
    assert _primary_arquivo_id(midias) == uuid.UUID(aid)
    assert _primary_arquivo_id([{"kind": "foto"}]) is None


async def test_process_media_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        entrada_service.telegram_media_service, "download_file", AsyncMock(return_value=b"img")
    )
    ingest = AsyncMock(
        return_value={"kind": "foto", "arquivo_id": str(uuid.uuid4()), "descricao": "parede"}
    )
    monkeypatch.setattr(entrada_service.media_service, "ingest_media", ingest)

    entrada = SimpleNamespace(
        raw_payload={
            "telegram": {"photo": [{"file_id": "F1", "file_size": 1}], "date": 1700000000}
        },
        event_id=None,
    )
    session = AsyncMock()

    results = await entrada_service._process_media(session, entrada, "OBRA-001")

    assert len(results) == 1
    assert results[0]["descricao"] == "parede"
    entrada_service.telegram_media_service.download_file.assert_awaited_once_with("F1")
    ingest.assert_awaited_once()


async def test_process_media_download_failure_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        entrada_service.telegram_media_service,
        "download_file",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(entrada_service.media_service, "ingest_media", AsyncMock())

    entrada = SimpleNamespace(
        raw_payload={"telegram": {"photo": [{"file_id": "F1"}]}}, event_id=None
    )
    session = AsyncMock()

    results = await entrada_service._process_media(session, entrada, "OBRA-001")

    assert len(results) == 1
    assert "erro" in results[0]
    entrada_service.media_service.ingest_media.assert_not_called()


async def test_process_media_no_telegram_returns_empty() -> None:
    entrada = SimpleNamespace(raw_payload={"text": "oi"}, event_id=None)
    session = AsyncMock()
    assert await entrada_service._process_media(session, entrada, "OBRA-001") == []


def test_build_reply_from_telegram_chat() -> None:
    entrada = SimpleNamespace(raw_payload={"telegram": {"chat": {"id": 555}}})
    reply = entrada_service._build_reply(
        entrada,
        {"tipo_documento": "rdo", "documento_id": "abcd1234ef", "precisa_aprovacao": True},
    )
    assert reply is not None
    chat_id, texto = reply
    assert chat_id == 555
    assert "rdo" in texto


def test_build_reply_none_without_telegram() -> None:
    entrada = SimpleNamespace(raw_payload={"text": "oi"})
    assert entrada_service._build_reply(entrada, {}) is None
