from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services import ingestao_service


class _Result:
    def __init__(self, *, one_or_none: object = None, one: object = None) -> None:
        self._one_or_none = one_or_none
        self._one = one

    def scalar_one_or_none(self) -> object:
        return self._one_or_none

    def scalar_one(self) -> object:
        return self._one


async def test_completed_replay_returns_cached_row() -> None:
    cached = SimpleNamespace(status="completed", response_json={"event_id": "evt", "ok": True})
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_Result(one_or_none=None), _Result(one=cached)])

    claim = await ingestao_service.claim_idempotency(
        session, event_id="evt", content_hash="h", obra_id="OBRA"
    )

    assert claim is cached
    assert claim.status == "completed"
    assert claim.response_json["event_id"] == "evt"


async def test_complete_idempotency_issues_update() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())

    await ingestao_service.complete_idempotency(
        session, event_id="evt", content_hash="h", obra_id="OBRA", result={"ok": True}
    )

    session.execute.assert_awaited_once()


async def test_fail_idempotency_issues_update() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())

    await ingestao_service.fail_idempotency(
        session, event_id="evt", content_hash="h", obra_id="OBRA", error="boom"
    )

    session.execute.assert_awaited_once()


async def test_concurrent_claims_first_owns_second_sees_processing() -> None:
    # Requisição 1 vence a corrida (INSERT bem-sucedido).
    s1 = AsyncMock()
    s1.execute = AsyncMock(side_effect=[_Result(one_or_none="evt:h:OBRA")])
    first = await ingestao_service.claim_idempotency(
        s1, event_id="evt", content_hash="h", obra_id="OBRA"
    )
    assert first is None

    # Requisição 2 conflita e enxerga o 'processing' já gravado.
    processing = SimpleNamespace(status="processing", response_json=None)
    s2 = AsyncMock()
    s2.execute = AsyncMock(side_effect=[_Result(one_or_none=None), _Result(one=processing)])
    second = await ingestao_service.claim_idempotency(
        s2, event_id="evt", content_hash="h", obra_id="OBRA"
    )
    assert second is processing
    assert second.status == "processing"
