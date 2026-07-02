from __future__ import annotations

import pytest
from sqlalchemy import select

from src.db.models import IdempotencyKey
from src.services import ingestao_service

pytestmark = pytest.mark.integration


async def test_claim_idempotency_is_atomic(db_session) -> None:
    await ingestao_service.ensure_obra(db_session, "OBRA-INT", nome="Obra Integração")
    await db_session.commit()

    first = await ingestao_service.claim_idempotency(
        db_session,
        event_id="evt-int-1",
        content_hash="hash-a",
        obra_id="OBRA-INT",
    )
    second = await ingestao_service.claim_idempotency(
        db_session,
        event_id="evt-int-1",
        content_hash="hash-a",
        obra_id="OBRA-INT",
    )
    await db_session.commit()

    assert first is None
    assert second is not None
    assert second.status == "processing"

    rows = await db_session.execute(select(IdempotencyKey))
    assert len(rows.scalars().all()) == 1


async def test_complete_and_fail_idempotency_persist(db_session) -> None:
    await ingestao_service.ensure_obra(db_session, "OBRA-INT", nome="Obra Integração")

    assert (
        await ingestao_service.claim_idempotency(
            db_session,
            event_id="evt-int-2",
            content_hash="hash-b",
            obra_id="OBRA-INT",
        )
        is None
    )
    await ingestao_service.complete_idempotency(
        db_session,
        event_id="evt-int-2",
        content_hash="hash-b",
        obra_id="OBRA-INT",
        result={"status": "queued", "entrada_id": "e-1"},
    )
    await db_session.commit()

    result = await db_session.execute(select(IdempotencyKey))
    row = result.scalar_one()
    assert row.status == "completed"
    assert row.response_json == {"status": "queued", "entrada_id": "e-1"}

    await ingestao_service.fail_idempotency(
        db_session,
        event_id="evt-int-2",
        content_hash="hash-b",
        obra_id="OBRA-INT",
        error="boom",
    )
    await db_session.commit()

    result = await db_session.execute(select(IdempotencyKey))
    row = result.scalar_one()
    assert row.status == "failed"
    assert row.error == "boom"
