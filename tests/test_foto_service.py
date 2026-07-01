from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import DocumentStatus
from src.core.errors import ValidationError
from src.db.models import Aprovacao, Documento, Foto, Obra
from src.services import foto_service


@pytest.mark.asyncio
async def test_approve_and_finalize_photo_report_generates_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_id = uuid.uuid4()
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste")
    doc = Documento(
        id=doc_id,
        obra_id="OBRA-001",
        tipo="relatorio_fotografico",
        titulo="Relatório",
        data_ref=date(2026, 6, 27),
        revisao="REV00",
        status=DocumentStatus.RASCUNHO_GERADO,
        bucket_key="obras/OBRA-001/03_rascunhos/relatorio_fotografico/2026-06-27/REV00/draft.html",
        metadata_json={"periodo": ["2026-06-27", "2026-06-27"], "fotos_count": 0},
    )
    session = MagicMock()
    added: list[object] = []
    calls = 0

    async def fake_execute(_stmt: object) -> MagicMock:
        nonlocal calls
        calls += 1
        result = MagicMock()
        if calls == 1:
            result.scalar_one_or_none.return_value = doc
        elif calls == 2:
            result.all.return_value = []
            result.scalars.return_value = result
        else:
            result.scalar_one_or_none.return_value = obra
        return result

    def fake_add(obj: object) -> None:
        added.append(obj)

    session.execute = fake_execute
    session.add.side_effect = fake_add
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    monkeypatch.setattr(
        "src.services.pdf_service.html_to_pdf",
        lambda _html: b"%PDF-1.4 foto",
    )
    monkeypatch.setattr(
        foto_service.bucket_service,
        "put_bytes",
        lambda key, _body, **_kwargs: f"s3://test-bucket/{key}",
    )
    monkeypatch.setattr(
        foto_service.bucket_service,
        "persist_sidecar_metadata",
        lambda _key, _metadata: "s3://test-bucket/meta.json",
    )

    with patch("src.services.foto_service.audit_service.log_event", new_callable=AsyncMock):
        result = await foto_service.approve_and_finalize_photo_report(
            session,
            documento_id=str(doc_id),
            aprovador="engenheiro",
            comentario="ok",
        )

    approvals = [obj for obj in added if isinstance(obj, Aprovacao)]
    assert len(approvals) == 1
    assert approvals[0].aprovado is True
    assert doc.status == DocumentStatus.FINALIZADO_VALIDADO
    assert result["formato"] == "pdf"
    assert result["status"] == DocumentStatus.FINALIZADO_VALIDADO.value
    assert "04_documentos_finais" in (doc.bucket_key or "")


@pytest.mark.asyncio
async def test_finalize_blocks_non_photo_report() -> None:
    doc_id = uuid.uuid4()
    doc = Documento(
        id=doc_id,
        obra_id="OBRA-001",
        tipo="rdo",
        titulo="RDO",
        data_ref=date(2026, 6, 27),
        revisao="REV00",
        status=DocumentStatus.APROVADO,
    )
    session = AsyncMock()
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = doc
    session.execute = AsyncMock(return_value=doc_result)

    with pytest.raises(ValidationError, match="relatório fotográfico"):
        await foto_service.finalize_photo_report(
            session, documento_id=str(doc_id), aprovador="engenheiro"
        )


@pytest.mark.asyncio
async def test_generate_photo_report_creates_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    foto = Foto(
        id=uuid.uuid4(),
        obra_id="OBRA-001",
        arquivo_id=uuid.uuid4(),
        data_foto=date(2026, 6, 27),
        descricao="Laje concretada",
        tags=["estrutura"],
    )
    arquivo = SimpleNamespace(
        bucket_key="obras/OBRA-001/foto.jpg",
        mime_type="image/jpeg",
    )
    session = MagicMock()
    calls = 0

    async def fake_execute(_stmt: object) -> MagicMock:
        nonlocal calls
        calls += 1
        result = MagicMock()
        if calls == 1:
            result.all.return_value = [(foto, arquivo)]
        else:
            result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        return result

    session.execute = fake_execute
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    monkeypatch.setattr(
        foto_service.bucket_service,
        "put_bytes",
        lambda key, _body, **_kwargs: f"s3://test/{key}",
    )

    with patch("src.services.foto_service.audit_service.log_event", new_callable=AsyncMock):
        result = await foto_service.generate_photo_report(
            session,
            obra_id="OBRA-001",
            periodo_inicio="2026-06-27",
            periodo_fim="2026-06-27",
        )

    assert result["fotos_incluidas"] == 1
    assert result["status"] == DocumentStatus.RASCUNHO_GERADO.value
    added_doc = next(obj for obj in session.add.call_args_list[0][0] if isinstance(obj, Documento))
    assert added_doc.tipo == "relatorio_fotografico"
