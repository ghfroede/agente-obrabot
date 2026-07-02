from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import openai_service
from src.services.openai_service import _heuristic_triagem


def test_heuristic_cronograma() -> None:
    result = _heuristic_triagem("Atualizar cronograma da obra")
    assert result.tipo_documento == "cronograma"


def test_heuristic_medicao() -> None:
    result = _heuristic_triagem("Medição do mês de junho")
    assert result.tipo_documento == "medicao"


def test_heuristic_audio() -> None:
    result = _heuristic_triagem("Segue áudio com observações do canteiro")
    assert result.tipo_documento == "audio_transcricao"


async def test_transcribe_audio_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_service, "_client", lambda: None)
    text = await openai_service.transcribe_audio(b"audio", "note.ogg")
    assert "indisponível" in text


async def test_describe_image_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_service, "_client", lambda: None)
    text = await openai_service.describe_image(b"img")
    assert "indisponível" in text


async def test_embed_text_without_api_key_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_service, "_client", lambda: None)
    assert await openai_service.embed_text("texto") == []


async def test_triagem_structured_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "tipo_documento": "foto_obra",
        "confianca": 0.8,
        "resumo": "foto",
        "campos_extraidos": {},
        "acao_sugerida": "delegar_para_foto_obra",
        "precisa_aprovacao": True,
    }
    msg = SimpleNamespace(content=f"```json\n{json.dumps(payload)}\n```")
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    create = AsyncMock(return_value=resp)
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(openai_service, "_client", lambda: fake_client)
    monkeypatch.setattr(
        openai_service,
        "get_settings",
        lambda: SimpleNamespace(openai_model="gpt-4o-mini"),
    )

    out = await openai_service.triagem_structured("foto da laje")

    assert out.tipo_documento == "foto_obra"
