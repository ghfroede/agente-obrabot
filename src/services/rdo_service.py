from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import GENERATED_BY, SCHEMA_VERSION, DocumentStatus
from src.core.errors import ValidationError
from src.db.models import Aprovacao, Documento, Obra
from src.services import audit_service, bucket_service, pdf_service
from src.services import common as service_common
from src.utils.dates import parse_date, today_iso, utc_now
from src.utils.filenames import build_document_filename, next_revision
from src.utils.hashing import sha256_hex

RDO_EDITABLE_STATUSES: tuple[DocumentStatus, ...] = (
    DocumentStatus.RASCUNHO_GERADO,
    DocumentStatus.EM_REVISAO,
    DocumentStatus.REPROVADO,
    DocumentStatus.CORRIGIDO,
)

_RDO_LIST_FIELDS: tuple[str, ...] = (
    "equipe",
    "equipamentos",
    "observacoes",
    "complementos_engenheiro",
)


def _require_rdo_document(doc: Documento) -> None:
    if doc.tipo != "rdo":
        raise ValidationError("Documento não é um RDO")


async def _require_approval(session: AsyncSession, doc: Documento) -> Aprovacao:
    return await service_common.require_approval(session, doc)


def _render_rdo_html(
    *, obra: Obra, data_ref: str, revisao: str, conteudo: dict[str, Any]
) -> bytes:
    env = service_common.jinja_env()
    template = env.get_template("rdo.html")
    html = template.render(
        obra=obra,
        data_ref=data_ref,
        revisao=revisao,
        conteudo=conteudo,
        generated_by=GENERATED_BY,
    )
    return html.encode("utf-8")


def _metadata_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _list_from_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.splitlines()
    elif isinstance(value, list):
        values = [str(item) for item in value]
    else:
        values = [str(value)]
    return [item.strip() for item in values if item.strip()]


def normalize_rdo_editable_fields(campos: dict[str, Any]) -> dict[str, Any]:
    clima_raw = campos.get("clima")
    clima = str(clima_raw).strip() if clima_raw is not None else ""
    normalized: dict[str, Any] = {"clima": clima or None}
    for field in _RDO_LIST_FIELDS:
        normalized[field] = _list_from_value(campos.get(field))
    return normalized


async def create_rdo_draft(
    session: AsyncSession,
    *,
    obra_id: str,
    data_ref: str,
    conteudo: dict[str, Any],
) -> dict[str, Any]:
    obra = await service_common.get_obra(session, obra_id)
    data_parsed = parse_date(data_ref) or parse_date(today_iso())

    existing = await session.execute(
        select(Documento.revisao).where(
            Documento.obra_id == obra_id,
            Documento.tipo == "rdo",
            Documento.data_ref == data_parsed,
        )
    )
    revisao = next_revision(list(existing.scalars().all()))

    body = _render_rdo_html(
        obra=obra, data_ref=data_ref, revisao=revisao, conteudo=conteudo
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


async def update_rdo_draft_fields(
    session: AsyncSession,
    *,
    documento_id: str,
    campos: dict[str, Any],
    editor: str,
) -> dict[str, Any]:
    doc = await service_common.get_documento(session, documento_id)
    if doc.tipo != "rdo":
        raise ValidationError("Documento não é um RDO")
    if doc.status not in RDO_EDITABLE_STATUSES:
        raise ValidationError(f"RDO não editável no status {doc.status.value}")
    if doc.data_ref is None:
        raise ValidationError("RDO sem data_ref")

    obra = await service_common.get_obra(session, doc.obra_id)
    data_ref = doc.data_ref.isoformat()
    metadata = _metadata_dict(doc.metadata_json)
    conteudo = _metadata_dict(metadata.get("conteudo"))
    normalized_fields = normalize_rdo_editable_fields(campos)
    conteudo["campos_editaveis"] = normalized_fields

    edited_at = utc_now().isoformat()
    metadata["conteudo"] = conteudo
    metadata["campos_editaveis"] = normalized_fields
    metadata["ultima_edicao"] = {"editor": editor, "edited_at": edited_at}

    body = _render_rdo_html(
        obra=obra, data_ref=data_ref, revisao=doc.revisao, conteudo=conteudo
    )
    key = doc.bucket_key
    if not key:
        filename = build_document_filename(
            tipo="RDO",
            obra_id=doc.obra_id,
            data_ref=data_ref,
            revisao=doc.revisao,
            status=DocumentStatus.EM_REVISAO,
            ext="html",
        )
        key = bucket_service.build_rdo_key(
            doc.obra_id, data_ref, doc.revisao, filename, slug=obra.slug, draft=True
        )

    uri = bucket_service.put_bytes(key, body, content_type="text/html", allow_overwrite=True)
    file_hash = sha256_hex(body)
    doc.status = DocumentStatus.EM_REVISAO
    doc.bucket_key = key
    doc.bucket_uri = uri
    doc.hash_sha256 = file_hash
    doc.metadata_json = metadata
    doc.updated_at = utc_now()

    bucket_service.persist_sidecar_metadata(
        key,
        {
            "documento_id": str(doc.id),
            "obra_id": doc.obra_id,
            "tipo": "rdo",
            "status": doc.status.value,
            "hash_sha256": file_hash,
            "edited_by": editor,
            "edited_at": edited_at,
            "source_entrada_ids": metadata.get("source_entrada_ids", []),
            "source_arquivo_ids": metadata.get("source_arquivo_ids", []),
        },
    )
    await audit_service.log_event(
        session,
        entidade="documento",
        entidade_id=str(doc.id),
        acao="rdo_campos_editados",
        obra_id=doc.obra_id,
        actor=editor,
        detalhes={"campos": sorted(normalized_fields.keys()), "bucket_key": key},
    )
    await session.commit()
    return {
        "documento_id": str(doc.id),
        "status": doc.status.value,
        "bucket_uri": uri,
        "hash_sha256": file_hash,
        "campos_editaveis": normalized_fields,
    }


async def _finalize_approved_rdo(
    session: AsyncSession,
    *,
    doc: Documento,
    approval: Aprovacao,
    aprovador: str,
    commit: bool,
) -> dict[str, Any]:
    obra = await service_common.get_obra(session, doc.obra_id)
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
    if commit:
        await session.commit()
    return {
        "documento_id": str(doc.id),
        "status": doc.status.value,
        "bucket_uri": uri,
        "formato": "pdf",
    }


async def finalize_rdo(
    session: AsyncSession,
    *,
    documento_id: str,
    aprovador: str,
) -> dict[str, Any]:
    doc = await service_common.get_documento(session, documento_id)
    _require_rdo_document(doc)

    approval = await _require_approval(session, doc)
    return await _finalize_approved_rdo(
        session,
        doc=doc,
        approval=approval,
        aprovador=aprovador,
        commit=True,
    )


async def approve_and_finalize_rdo(
    session: AsyncSession,
    *,
    documento_id: str,
    aprovador: str,
    comentario: str | None = None,
) -> dict[str, Any]:
    doc = await service_common.get_documento(session, documento_id)
    _require_rdo_document(doc)
    if doc.status == DocumentStatus.FINALIZADO_VALIDADO:
        raise ValidationError("RDO já finalizado")

    approval = Aprovacao(
        documento_id=doc.id,
        aprovador=aprovador,
        aprovado=True,
        comentario=comentario,
    )
    session.add(approval)
    doc.status = DocumentStatus.APROVADO
    doc.updated_at = utc_now()
    await audit_service.log_event(
        session,
        entidade="documento",
        entidade_id=str(doc.id),
        acao="aprovado",
        obra_id=doc.obra_id,
        actor=aprovador,
        detalhes={"comentario": comentario, "origem": "rdo_aprovar_finalizar"},
    )
    await session.flush()

    final = await _finalize_approved_rdo(
        session,
        doc=doc,
        approval=approval,
        aprovador=aprovador,
        commit=False,
    )
    await session.commit()
    return {
        **final,
        "aprovacao": {
            "aprovado": True,
            "aprovador": aprovador,
            "comentario": comentario,
        },
    }
