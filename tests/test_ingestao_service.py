from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agent.triagem import classify_entry
from src.services import ingestao_service, openai_service


class _Result:
    def __init__(self, *, one_or_none: object = None, one: object = None) -> None:
        self._one_or_none = one_or_none
        self._one = one

    def scalar_one_or_none(self) -> object:
        return self._one_or_none

    def scalar_one(self) -> object:
        return self._one


def test_idempotency_key_format() -> None:
    assert ingestao_service.idempotency_key("evt", "hash", "OBRA-001") == "evt:hash:OBRA-001"


async def test_claim_returns_none_when_inserted() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_Result(one_or_none="evt:hash:OBRA")])

    res = await ingestao_service.claim_idempotency(
        session, event_id="evt", content_hash="hash", obra_id="OBRA"
    )

    assert res is None
    session.execute.assert_awaited_once()


async def test_claim_returns_existing_on_conflict() -> None:
    existing = SimpleNamespace(status="processing", response_json=None)
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_Result(one_or_none=None), _Result(one=existing)]
    )

    res = await ingestao_service.claim_idempotency(
        session, event_id="evt", content_hash="hash", obra_id="OBRA"
    )

    assert res is existing
    assert session.execute.await_count == 2


async def test_classify_entry_heuristic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_service, "_client", lambda: None)
    monkeypatch.setattr(
        "src.agent.triagem.get_settings", lambda: SimpleNamespace(openai_api_key="")
    )

    result = await classify_entry("Gerar RDO de hoje", obra_id="OBRA-001", author="eng")

    assert result["modo"] == "heuristic"
    assert result["tipo_documento"] == "rdo"
    assert result["obra_id"] == "OBRA-001"
