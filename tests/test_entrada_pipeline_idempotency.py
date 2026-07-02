from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.db.models import Triagem
from src.schemas.domain import TriagemOutput
from src.services import entrada_service
from src.services.entrada_service import PENDING_OBRA_STATUS


def _triagem_output() -> TriagemOutput:
    return TriagemOutput(
        tipo_documento="rdo",
        confianca=0.9,
        resumo="resumo",
        campos_extraidos={},
        acao_sugerida="gerar_rdo",
        precisa_aprovacao=True,
    )


async def test_process_skips_when_documento_and_triagem_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entrada_id = uuid4()
    doc_id = uuid4()
    triagem_id = uuid4()
    entrada = SimpleNamespace(
        id=entrada_id,
        obra_id="OBRA-001",
        event_id="evt-1",
        source="openclaw",
        text="oi",
        raw_payload={},
        storage_key="key",
        storage_uri="s3://bucket/key",
        author=None,
        data_ref=None,
    )
    obra = SimpleNamespace(id="OBRA-001", slug="obra-001")
    doc = SimpleNamespace(
        id=doc_id,
        status=SimpleNamespace(value="triado"),
        metadata_json={"midias": []},
    )
    triagem_row = SimpleNamespace(
        id=triagem_id,
        tipo_documento="RDO",
        confianca=0.9,
        resumo="resumo",
        acao_sugerida="gerar_rdo",
        precisa_aprovacao=True,
    )

    session = AsyncMock()
    monkeypatch.setattr(
        entrada_service.ingestao_service, "ensure_obra", AsyncMock(return_value=obra)
    )
    monkeypatch.setattr(
        entrada_service,
        "_load_existing_artifacts",
        AsyncMock(return_value=(doc, triagem_row)),
    )
    process_media = AsyncMock()
    monkeypatch.setattr(entrada_service, "_process_media", process_media)

    result = await entrada_service._process(session, entrada)

    assert result["retomado"] is True
    assert result["documento_id"] == str(doc_id)
    assert result["triagem_id"] == str(triagem_id)
    process_media.assert_not_awaited()


async def test_run_entrada_pipeline_calls_fail_idempotency_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entrada_id = uuid4()
    entrada = SimpleNamespace(
        id=entrada_id,
        obra_id="OBRA-001",
        status="received",
        idempotency_key="evt-1:hash:OBRA-001",
        event_id="evt-1",
        task_id=None,
    )

    session = AsyncMock()
    session.get = AsyncMock(return_value=entrada)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    class _SessionCtx:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(entrada_service, "AsyncSessionLocal", lambda: _SessionCtx())
    monkeypatch.setattr(entrada_service, "_process", AsyncMock(side_effect=RuntimeError("boom")))
    fail = AsyncMock()
    monkeypatch.setattr(entrada_service.ingestao_service, "fail_idempotency", fail)
    monkeypatch.setattr(entrada_service, "_mark_task", AsyncMock())

    with pytest.raises(RuntimeError, match="boom"):
        await entrada_service.run_entrada_pipeline(str(entrada_id))

    fail.assert_awaited_once()
    assert fail.await_args.kwargs["event_id"] == "evt-1"
    assert fail.await_args.kwargs["content_hash"] == "hash"
    assert fail.await_args.kwargs["obra_id"] == "OBRA-001"


async def test_process_reuses_bucket_when_storage_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entrada_id = uuid4()
    entrada = SimpleNamespace(
        id=entrada_id,
        obra_id="OBRA-001",
        event_id="evt-1",
        source="openclaw",
        text="oi",
        raw_payload={},
        storage_key="existing-key",
        storage_uri="s3://bucket/existing-key",
        author=None,
        data_ref=None,
    )
    obra = SimpleNamespace(id="OBRA-001", slug="obra-001")
    triagem_row = Triagem(
        obra_id="OBRA-001",
        entrada_id=entrada_id,
        tipo_documento="RDO",
        confianca=0.9,
        resumo="resumo",
        campos_extraidos={},
        acao_sugerida="gerar_rdo",
        precisa_aprovacao=True,
        modelo="heuristic",
    )

    session = AsyncMock()
    monkeypatch.setattr(
        entrada_service.ingestao_service, "ensure_obra", AsyncMock(return_value=obra)
    )
    monkeypatch.setattr(
        entrada_service,
        "_load_existing_artifacts",
        AsyncMock(return_value=(None, None)),
    )
    persist = MagicMock()
    monkeypatch.setattr(entrada_service.bucket_service, "persist_entrada_bruta", persist)
    monkeypatch.setattr(entrada_service, "_process_media", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        entrada_service.openai_service,
        "triagem_structured",
        AsyncMock(return_value=_triagem_output()),
    )
    monkeypatch.setattr(
        entrada_service.ingestao_service,
        "save_triagem",
        AsyncMock(return_value=triagem_row),
    )
    monkeypatch.setattr(entrada_service, "_find_telegram_message_id", AsyncMock(return_value=None))
    monkeypatch.setattr(entrada_service.bucket_service, "persist_triagem_json", MagicMock())
    monkeypatch.setattr(entrada_service.audit_service, "log_event", AsyncMock())
    session.add = MagicMock()
    session.flush = AsyncMock()

    await entrada_service._process(session, entrada)

    persist.assert_not_called()
    assert entrada.storage_key == "existing-key"


async def test_process_pending_obra_short_circuits() -> None:
    entrada = SimpleNamespace(id=uuid4(), obra_id=None)
    session = AsyncMock()
    result = await entrada_service._process(session, entrada)
    assert result["status"] == PENDING_OBRA_STATUS
