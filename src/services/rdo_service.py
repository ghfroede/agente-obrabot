from __future__ import annotations

import uuid
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import GENERATED_BY, SCHEMA_VERSION, DocumentStatus
from src.core.errors import ApprovalRequiredError, NotFoundError
from src.db.models import Aprovacao, Documento, Obra
from src.services import audit_service, bucket_service, pdf_service
from src.utils.dates import parse_date, today_iso, utc_now
from src.utils.filenames import build_document_filename, next_revision
from src.utils.hashing import sha256_hex


def _jinja_env() -> Environment:
    settings = get_settings()
    return Environment(
        loader=FileSystemLoader(settings.templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )


async def _get_obra(session: AsyncSession, obra_id: str) -> Obra:
    result = await session.execute(select(Obra).where(Obra.id == obra_id))
    obra = result.scalar_one_or_none()
    if obra is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    return obra


async def _require_approval(session: AsyncSession, doc: Documento) -> Aprovacao:
    if doc.status != DocumentStatus.APROVADO:
        raise ApprovalRequiredError(
            f"Documento deve estar APROVADO para finalizar (atual: {doc.status.value})"
        )
    result = await session.execute(
        select(Aprovacao)
        .where(Aprovacao.documento_id == doc.id, Aprovacao.aprovado.is_(True))
        .order_by(Aprovacao.created_at.desc())
        .limit(1)
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise ApprovalRequiredError("Nenhuma aprovação humana registrada para este documento")
    return approval


async def create_rdo_draft(
    session: AsyncSession,
    *,
    obra_id: str,
    data_ref: str,
    conteudo: dict[str, Any],
) -> dict[str, Any]:
    obra = await _get_obra(session, obra_id)
    data_parsed = parse_date(data_ref) or parse_date(today_iso())

    existing = await session.execute(
        select(Documento.revisao).where(
            Documento.obra_id == obra_id,
            Documento.tipo == "rdo",
            Documento.data_ref == data_parsed,
        )
    )
    revisao = next_revision(list(existing.scalars().all()))

    env = _jinja_env()
    template = env.get_template("rdo.html")
    html = template.render(
        obra=obra,
        data_ref=data_ref,
        revisao=revisao,
        conteudo=conteudo,
        generated_by=GENERATED_BY,
    )
    filename = build_document_filename(
        tipo="RDO",
        obra_id=obra_id,
        data_ref=data_ref,
        revisao=revisao,
        status=DocumentStatus.RASCUNHO_GERADO,
        ext="html",
    )
    key = bucket_service.build_rdo_key(
        obra_id, data_ref, revisao, filename, slug=obra.slug, draft=True
    )
    body = html.encode("utf-8")
    uri = bucket_service.put_bytes(key, body, content_type="text/html", allow_overwrite=True)
    file_hash = sha256_hex(body)
    source_entrada_ids = conteudo.get("source_entrada_ids", [])
    source_arquivo_ids = conteudo.get("source_arquivo_ids", [])

    doc = Documento(
        obra_id=obra_id,
        tipo="rdo",
        titulo=f"RDO {obra_id} {data_ref}",
        data_ref=data_parsed,
        revisao=revisao,
        status=DocumentStatus.RASCUNHO_GERADO,
        bucket_key=key,
        bucket_uri=uri,
        hash_sha256=file_hash,
        metadata_json={
            "conteudo": conteudo,
            "formato": "html",
            "source_entrada_ids": source_entrada_ids,
            "source_arquivo_ids": source_arquivo_ids,
            "campos_editaveis": conteudo.get("campos_editaveis", {}),
        },
    )
    session.add(doc)
    await session.flush()
    bucket_service.persist_sidecar_metadata(
        key,
        {
            "documento_id": str(doc.id),
            "obra_id": obra_id,
            "tipo": "rdo",
            "status": doc.status.value,
            "hash_sha256": file_hash,
            "source_entrada_ids": source_entrada_ids,
            "source_arquivo_ids": source_arquivo_ids,
        },
    )
    await audit_service.log_event(
        session,
        entidade="documento",
        entidade_id=str(doc.id),
        acao="rdo_rascunho_gerado",
        obra_id=obra_id,
        detalhes={"bucket_key": key},
    )
    await session.commit()
    return {
        "documento_id": str(doc.id),
        "status": doc.status.value,
        "revisao": revisao,
        "bucket_uri": uri,
    }


async def finalize_rdo(
    session: AsyncSession,
    *,
    documento_id: str,
    aprovador: str,
) -> dict[str, Any]:
    doc_id = uuid.UUID(documento_id)
    result = await session.execute(select(Documento).where(Documento.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError(f"Documento {documento_id} não encontrado")

    approval = await _require_approval(session, doc)

    obra = await _get_obra(session, doc.obra_id)
    data_ref = doc.data_ref.isoformat() if doc.data_ref else today_iso()

    draft_key = doc.bucket_key or ""
    html_bytes = (
        bucket_service.get_bytes(draft_key)
        if draft_key
        else b"<html><body><h1>RDO</h1></body></html>"
    )
    html = html_bytes.decode("utf-8", errors="replace")
    pdf_bytes = pdf_service.html_to_pdf(html)

    filename = build_document_filename(
        tipo="RDO",
        obra_id=doc.obra_id,
        data_ref=data_ref,
        revisao=doc.revisao,
        status=DocumentStatus.FINALIZADO_VALIDADO,
        ext="pdf",
    )
    final_key = bucket_service.build_rdo_key(
        doc.obra_id,
        data_ref,
        doc.revisao,
        filename,
        slug=obra.slug,
        draft=False,
    )
    uri = bucket_service.put_bytes(
        final_key, pdf_bytes, content_type="application/pdf", allow_overwrite=False
    )
    file_hash = sha256_hex(pdf_bytes)
    doc.status = DocumentStatus.FINALIZADO_VALIDADO
    doc.bucket_key = final_key
    doc.bucket_uri = uri
    doc.hash_sha256 = file_hash
    doc.updated_at = utc_now()
    bucket_service.persist_sidecar_metadata(
        final_key,
        {
            "documento_id": str(doc.id),
            "obra_id": doc.obra_id,
            "tipo": "RDO",
            "data_ref": data_ref,
            "status": doc.status.value,
            "hash_sha256": file_hash,
            "aprovado_por": approval.aprovador,
            "aprovado_em": (
                approval.created_at.isoformat()
                if approval.created_at is not None
                else utc_now().isoformat()
            ),
            "gerado_em": utc_now().isoformat(),
            "schema_version": SCHEMA_VERSION,
        },
    )
    await audit_service.log_event(
        session,
        entidade="documento",
        entidade_id=str(doc.id),
        acao="rdo_finalizado",
        obra_id=doc.obra_id,
        actor=aprovador,
        detalhes={"bucket_key": final_key, "formato": "pdf"},
    )
    await session.commit()
    return {
        "documento_id": str(doc.id),
        "status": doc.status.value,
        "bucket_uri": uri,
        "formato": "pdf",
    }
