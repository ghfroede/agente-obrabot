from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.core.constants import DocumentStatus
from src.db.models import Aprovacao, Documento, Obra
from src.services import ingestao_service, rdo_service

pytestmark = pytest.mark.integration


@pytest.fixture
def local_bucket(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    settings = SimpleNamespace(
        s3_configured=False,
        local_bucket_path=str(tmp_path),
        s3_bucket_name="test-bucket",
    )
    monkeypatch.setattr(rdo_service.bucket_service, "get_settings", lambda: settings)


async def test_rdo_create_draft_and_approve_finalizes_pdf(
    db_session, local_bucket: None
) -> None:
    db_session.add(
        Obra(id="OBRA-INT", nome="Obra Integração", slug="obra-int", status="ativa")
    )
    await db_session.commit()

    conteudo = {
        "source_entrada_ids": [],
        "source_arquivo_ids": [],
        "resumo_operacional": {"texto": "Concretagem concluída"},
        "servicos": [],
        "pendencias": [],
        "fotos": [],
        "audios": [],
        "documentos_brutos": [],
        "campos_editaveis": {"clima": "Ensolarado", "equipe": ["Equipe A"]},
    }
    draft = await rdo_service.create_rdo_draft(
        db_session,
        obra_id="OBRA-INT",
        data_ref="2026-06-27",
        conteudo=conteudo,
    )
    assert draft["status"] == DocumentStatus.RASCUNHO_GERADO.value

    doc_result = await db_session.execute(
        select(Documento).where(Documento.id == uuid.UUID(draft["documento_id"]))
    )
    doc = doc_result.scalar_one()
    assert doc.tipo == "rdo"
    assert doc.data_ref == date(2026, 6, 27)

    final = await rdo_service.approve_and_finalize_rdo(
        db_session,
        documento_id=str(doc.id),
        aprovador="engenheiro@teste",
        comentario="Aprovado em teste de integração",
    )

    assert final["status"] == DocumentStatus.FINALIZADO_VALIDADO.value
    assert final["formato"] == "pdf"
    assert final["aprovacao"]["aprovado"] is True

    refreshed = await db_session.get(Documento, doc.id)
    assert refreshed is not None
    assert refreshed.status == DocumentStatus.FINALIZADO_VALIDADO
    assert refreshed.bucket_key is not None
    assert refreshed.bucket_key.endswith(".pdf")

    approvals = await db_session.execute(
        select(Aprovacao).where(Aprovacao.documento_id == doc.id)
    )
    assert len(approvals.scalars().all()) == 1

    # Obra permanece acessível após fluxo completo.
    obra = await ingestao_service.ensure_obra(db_session, "OBRA-INT")
    assert obra.nome == "Obra Integração"
