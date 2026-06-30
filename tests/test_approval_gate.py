from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.routes import documentos as documentos_route
from src.core.constants import DocumentStatus
from src.core.errors import ApprovalRequiredError, BucketConflictError
from src.db.models import Aprovacao, Documento, Obra
from src.services import bucket_service, rdo_service


def test_bucket_taxonomy_keys() -> None:
    entrada = bucket_service.build_entrada_bruta_key(
        "OBRA-001",
        "evt-1",
        slug="obra-teste",
        message_id=42,
        data_ref=date(2026, 6, 27),
        entrada_id="entrada-1",
    )
    assert entrada == (
        "obras/OBRA-001-obra-teste/01_entrada_bruta/telegram/"
        "2026/06/27/entrada_entrada-1/envelope.json"
    )

    triagem = bucket_service.build_triagem_key("OBRA-001", "t1", slug="obra-teste")
    assert "/03_triagem/classificacoes/" in triagem

    foto = bucket_service.build_arquivo_key(
        "OBRA-001", "foto", "a" * 64, "jpg", slug="obra-teste", data_ref="2026-06-27"
    )
    assert foto == "obras/OBRA-001-obra-teste/06_fotos/brutas/2026-06-27/aaaaaaaaaaaaaaaa.jpg"

    audio = bucket_service.build_arquivo_key(
        "OBRA-001", "audio", "b" * 64, "ogg", slug="obra-teste"
    )
    assert "/02_midias/audio/" in audio

    rdo_draft = bucket_service.build_rdo_key(
        "OBRA-001", "2026-06-27", "REV00", "rdo.html", slug="obra-teste", draft=True
    )
    assert "/05_RDO/rascunhos/" in rdo_draft

    rdo_final = bucket_service.build_rdo_key(
        "OBRA-001", "2026-06-27", "REV00", "rdo.pdf", slug="obra-teste", draft=False
    )
    assert "/05_RDO/finalizados_pdf/" in rdo_final


def _bucket_settings(local_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        s3_configured=False,
        local_bucket_path=local_path,
        s3_bucket_name="test-bucket",
    )


def test_final_overwrite_blocked(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.services.bucket_service.get_settings",
        lambda: _bucket_settings(str(tmp_path / "bucket")),
    )
    key = "test/final.pdf"
    bucket_service.put_bytes(key, b"v1", allow_overwrite=False)
    with pytest.raises(BucketConflictError):
        bucket_service.put_bytes(key, b"v2", allow_overwrite=False)


@pytest.mark.asyncio
async def test_rdo_gerar_uses_aggregator_and_creates_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conteudo = {
        "source_entrada_ids": ["entrada-1"],
        "source_arquivo_ids": ["arquivo-1"],
    }
    aggregate = AsyncMock(return_value=conteudo)
    create_draft = AsyncMock(
        return_value={
            "documento_id": "doc-1",
            "status": DocumentStatus.RASCUNHO_GERADO.value,
            "revisao": "REV00",
            "bucket_uri": "s3://bucket/rdo.html",
        }
    )
    monkeypatch.setattr(documentos_route.rdo_aggregator_service, "aggregate_daily_rdo", aggregate)
    monkeypatch.setattr(documentos_route.rdo_service, "create_rdo_draft", create_draft)
    body = documentos_route.RdoGenerateRequest(obra_id="OBRA-001", data_ref="2026-06-27")
    session = AsyncMock()

    result = await documentos_route.rdo_gerar(body, session)

    aggregate.assert_awaited_once_with(
        session, obra_id="OBRA-001", data_ref="2026-06-27"
    )
    create_draft.assert_awaited_once_with(
        session,
        obra_id="OBRA-001",
        data_ref="2026-06-27",
        conteudo=conteudo,
    )
    assert result["source_entrada_ids"] == ["entrada-1"]
    assert result["source_arquivo_ids"] == ["arquivo-1"]


@pytest.mark.asyncio
async def test_update_rdo_draft_fields_regenerates_html_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_id = uuid.uuid4()
    obra = Obra(id="OBRA-001", nome="Obra Um", slug="obra-um")
    doc = Documento(
        id=doc_id,
        obra_id="OBRA-001",
        tipo="rdo",
        titulo="RDO",
        data_ref=date(2026, 6, 27),
        revisao="REV00",
        status=DocumentStatus.RASCUNHO_GERADO,
        bucket_key="obras/OBRA-001-obra-um/05_RDO/rascunhos/2026-06-27/REV00/draft.html",
        metadata_json={
            "conteudo": {
                "source_entrada_ids": ["entrada-1"],
                "source_arquivo_ids": ["arquivo-1"],
                "resumo_operacional": {},
                "servicos": [],
                "pendencias": [],
                "fotos": [],
                "audios": [],
                "documentos_brutos": [],
                "campos_editaveis": {},
            },
            "source_entrada_ids": ["entrada-1"],
            "source_arquivo_ids": ["arquivo-1"],
        },
    )
    session = AsyncMock()
    calls = 0

    async def fake_execute(_stmt: object) -> MagicMock:
        nonlocal calls
        calls += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = doc if calls == 1 else obra
        return result

    captured: dict[str, object] = {}

    def fake_put_bytes(key: str, body: bytes, **kwargs: object) -> str:
        captured["key"] = key
        captured["body"] = body
        captured["kwargs"] = kwargs
        return f"s3://test-bucket/{key}"

    session.execute = fake_execute
    session.commit = AsyncMock()
    monkeypatch.setattr(rdo_service.bucket_service, "put_bytes", fake_put_bytes)
    monkeypatch.setattr(
        rdo_service.bucket_service,
        "persist_sidecar_metadata",
        lambda _key, _metadata: "s3://test-bucket/meta.json",
    )

    with patch("src.services.rdo_service.audit_service.log_event", new_callable=AsyncMock):
        result = await rdo_service.update_rdo_draft_fields(
            session,
            documento_id=str(doc_id),
            editor="engenheiro",
            campos={
                "clima": " Sol ",
                "equipe": "Mestre João\n\n2 pedreiros",
                "equipamentos": "Betoneira",
                "observacoes": "Sem interferências.",
                "complementos_engenheiro": "Liberar frente amanhã.",
            },
        )

    assert result["status"] == DocumentStatus.EM_REVISAO.value
    assert doc.status == DocumentStatus.EM_REVISAO
    assert doc.metadata_json is not None
    assert doc.metadata_json["campos_editaveis"]["clima"] == "Sol"
    assert doc.metadata_json["campos_editaveis"]["equipe"] == [
        "Mestre João",
        "2 pedreiros",
    ]
    assert b"Sol" in captured["body"]
    assert captured["kwargs"] == {"content_type": "text/html", "allow_overwrite": True}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_blocked_when_not_approved() -> None:
    doc_id = uuid.uuid4()
    doc = Documento(
        id=doc_id,
        obra_id="OBRA-001",
        tipo="rdo",
        titulo="RDO",
        data_ref=date(2026, 6, 27),
        revisao="REV00",
        status=DocumentStatus.RASCUNHO_GERADO,
        bucket_key="draft.html",
    )
    session = AsyncMock()
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = doc
    session.execute = AsyncMock(return_value=doc_result)

    with pytest.raises(ApprovalRequiredError, match="APROVADO"):
        await rdo_service.finalize_rdo(
            session, documento_id=str(doc_id), aprovador="engenheiro"
        )


@pytest.mark.asyncio
async def test_finalize_blocked_without_approval_record() -> None:
    doc_id = uuid.uuid4()
    doc = Documento(
        id=doc_id,
        obra_id="OBRA-001",
        tipo="rdo",
        titulo="RDO",
        data_ref=date(2026, 6, 27),
        revisao="REV00",
        status=DocumentStatus.APROVADO,
        bucket_key="draft.html",
    )
    session = AsyncMock()
    calls = 0

    async def fake_execute(stmt: object) -> MagicMock:
        nonlocal calls
        calls += 1
        result = MagicMock()
        if calls == 1:
            result.scalar_one_or_none.return_value = doc
        else:
            result.scalar_one_or_none.return_value = None
        return result

    session.execute = fake_execute

    with pytest.raises(ApprovalRequiredError, match="aprovação humana"):
        await rdo_service.finalize_rdo(
            session, documento_id=str(doc_id), aprovador="engenheiro"
        )


@pytest.mark.asyncio
async def test_finalize_generates_pdf_when_approved(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    doc_id = uuid.uuid4()
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste")
    doc = Documento(
        id=doc_id,
        obra_id="OBRA-001",
        tipo="rdo",
        titulo="RDO",
        data_ref=date(2026, 6, 27),
        revisao="REV00",
        status=DocumentStatus.APROVADO,
        bucket_key="obras/OBRA-001-obra-teste/05_RDO/rascunhos/2026-06-27/REV00/draft.html",
    )
    approval = Aprovacao(
        documento_id=doc_id,
        aprovador="engenheiro",
        aprovado=True,
        created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )

    session = AsyncMock()
    calls = 0

    async def fake_execute(_stmt: object) -> MagicMock:
        nonlocal calls
        calls += 1
        result = MagicMock()
        if calls == 1:
            result.scalar_one_or_none.return_value = doc
        elif calls == 2:
            result.scalar_one_or_none.return_value = approval
        else:
            result.scalar_one_or_none.return_value = obra
        return result

    session.execute = fake_execute
    session.commit = AsyncMock()

    monkeypatch.setattr(
        "src.services.bucket_service.get_settings",
        lambda: SimpleNamespace(
            s3_configured=False,
            local_bucket_path=str(tmp_path / "bucket"),
            s3_bucket_name="test-bucket",
            templates_dir="src/templates",
        ),
    )
    monkeypatch.setattr(
        bucket_service,
        "get_bytes",
        lambda _k: b"<html><body><h1>RDO</h1></body></html>",
    )
    monkeypatch.setattr(
        "src.services.pdf_service.html_to_pdf",
        lambda _html: b"%PDF-1.4 smoke",
    )

    with patch("src.services.rdo_service.audit_service.log_event", new_callable=AsyncMock):
        result = await rdo_service.finalize_rdo(
            session, documento_id=str(doc_id), aprovador="engenheiro"
        )

    assert result["formato"] == "pdf"
    assert result["status"] == DocumentStatus.FINALIZADO_VALIDADO.value
    assert "finalizados_pdf" in (doc.bucket_key or "")
