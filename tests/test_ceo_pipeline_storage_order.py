from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.agent import ceo


def _settings(*, s3: bool = True) -> SimpleNamespace:
    return SimpleNamespace(s3_configured=s3, agent_name="Obrabot")


async def test_persists_raw_before_classify(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(ceo, "get_settings", lambda: _settings(s3=True))

    def fake_persist(**_kwargs: Any) -> str:
        calls.append("persist")
        return "s3://bucket/raw.json"

    async def fake_classify(_message: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append("classify")
        return {"tipo_documento": "rdo", "pendencias": [], "acao_sugerida": "x"}

    monkeypatch.setattr(ceo, "persist_raw_entry", fake_persist)
    monkeypatch.setattr(ceo, "classify_entry", fake_classify)

    result = await ceo.run_ceo_pipeline({"message": "alvenaria pav 2", "obra_id": "OBRA-001"})

    assert calls == ["persist", "classify"], "raw deve ser persistido ANTES da IA"
    assert result["storage_uri"] == "s3://bucket/raw.json"


async def test_skips_storage_when_s3_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(ceo, "get_settings", lambda: _settings(s3=False))

    def fake_persist(**_kwargs: Any) -> str:
        calls.append("persist")
        return "unused"

    async def fake_classify(_message: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append("classify")
        return {"tipo_documento": "rdo", "pendencias": [], "acao_sugerida": "x"}

    monkeypatch.setattr(ceo, "persist_raw_entry", fake_persist)
    monkeypatch.setattr(ceo, "classify_entry", fake_classify)

    result = await ceo.run_ceo_pipeline({"message": "alvenaria", "obra_id": "OBRA-001"})

    assert calls == ["classify"]
    assert result["storage_uri"] is None


async def test_empty_message_raises() -> None:
    with pytest.raises(ValueError):
        await ceo.run_ceo_pipeline({"message": "   "})
