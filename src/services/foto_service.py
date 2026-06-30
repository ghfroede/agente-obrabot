from __future__ import annotations

import base64
import uuid
from datetime import date
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import GENERATED_BY, SCHEMA_VERSION, DocumentStatus
from src.core.errors import ApprovalRequiredError, NotFoundError, ValidationError
from src.db.models import Aprovacao, Arquivo, Documento, Foto, Obra
from src.services import audit_service, bucket_service, pdf_service
from src.utils.dates import parse_date, utc_now
from src.utils.filenames import build_photo_report_filename, next_revision
from src.utils.hashing import sha256_hex

PHOTO_REPORT_TYPE = "relatorio_fotografico"


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


async def _get_documento(session: AsyncSession, documento_id: str | uuid.UUID) -> Documento:
    doc_id = documento_id if isinstance(documento_id, uuid.UUID) else uuid.UUID(str(documento_id))
    result = await session.execute(select(Documento).where(Documento.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError(f"Documento {documento_id} não encontrado")
    return doc


def _require_photo_report_document(doc: Documento) -> None:
    if doc.tipo != PHOTO_REPORT_TYPE:
        raise ValidationError("Documento não é um relatório fotográfico")


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


def _period_from_metadata(metadata: dict[str, Any] | None) -> tuple[str, str]:
    periodo = (metadata or {}).get("periodo") or []
    if isinstance(periodo, list) and len(periodo) >= 2:
        return str(periodo[0]), str(periodo[1])
    return "", ""


async def _load_fotos_with_arquivos(
    session: AsyncSession,
    *,
    obra_id: str,
    inicio: date | None,
    fim: date | None,
) -> list[tuple[Foto, Arquivo | None]]:
    query = (
        select(Foto, Arquivo)
        .outerjoin(Arquivo, Foto.arquivo_id == Arquivo.id)
        .where(Foto.obra_id == obra_id)
    )
    if inicio and fim:
        query = query.where(and_(Foto.data_foto >= inicio, Foto.data_foto <= fim))
    result = await session.execute(query.order_by(Foto.data_foto.asc()))
    return list(result.all())


def _fotos_to_template_items(
    rows: list[tuple[Foto, Arquivo | None]],
    *,
    embed_images: bool,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for foto, arquivo in rows:
        item: dict[str, Any] = {
            "data_foto": foto.data_foto,
            "descricao": foto.descricao,
            "tags": foto.tags or [],
            "image_data_uri": None,
        }
        if embed_images and arquivo and arquivo.bucket_key:
            try:
                img_bytes = bucket_service.get_bytes(arquivo.bucket_key)
                mime = arquivo.mime_type or "image/jpeg"
                b64 = base64.b64encode(img_bytes).decode("ascii")
                item["image_data_uri"] = f"data:{mime};base64,{b64}"
            except Exception:
                item["image_data_uri"] = None
        items.append(item)
    return items


def _render_photo_report_html(
    *,
    obra_id: str,
    periodo_inicio: str,
    periodo_fim: str,
    revisao: str,
    fotos: list[dict[str, Any]],
) -> str:
    env = _jinja_env()
    template = env.get_template("relatorio_fotografico.html")
    return template.render(
        obra_id=obra_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        revisao=revisao,
        fotos=fotos,
        generated_by=GENERATED_BY,
    )


async def generate_photo_report(
    session: AsyncSession,
    *,
    obra_id: str,
    periodo_inicio: str,
    periodo_fim: str,
) -> dict[str, Any]:
    inicio = parse_date(periodo_inicio)
    fim = parse_date(periodo_fim)
    rows = await _load_fotos_with_arquivos(session, obra_id=obra_id, inicio=inicio, fim=fim)

    existing = await session.execute(
        select(Documento.revisao).where(
            Documento.obra_id == obra_id,
            Documento.tipo == PHOTO_REPORT_TYPE,
        )
    )
    revisao = next_revision(list(existing.scalars().all()))

    fotos = _fotos_to_template_items(rows, embed_images=False)
    html = _render_photo_report_html(
        obra_id=obra_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        revisao=revisao,
        fotos=fotos,
    )
    filename = build_photo_report_filename(
        obra_id, periodo_inicio, periodo_fim, revisao, final=False
    )
    html_name = filename.replace(".pdf", ".html")
    key = bucket_service.build_documento_key(
        obra_id, PHOTO_REPORT_TYPE, periodo_inicio, revisao, html_name, draft=True
    )
    body = html.encode("utf-8")
    uri = bucket_service.put_bytes(key, body, content_type="text/html")
    file_hash = sha256_hex(body)

    doc = Documento(
        obra_id=obra_id,
        tipo=PHOTO_REPORT_TYPE,
        titulo=f"Relatório fotográfico {periodo_inicio} a {periodo_fim}",
        data_ref=inicio or date.today(),
        revisao=revisao,
        status=DocumentStatus.RASCUNHO_GERADO,
        bucket_key=key,
        bucket_uri=uri,
        hash_sha256=file_hash,
        metadata_json={
            "fotos_count": len(fotos),
            "periodo": [periodo_inicio, periodo_fim],
        },
    )
    session.add(doc)
    await session.flush()
    await audit_service.log_event(
        session,
        entidade="documento",
        entidade_id=str(doc.id),
        acao="relatorio_fotografico_rascunho",
        obra_id=obra_id,
        detalhes={"fotos": len(fotos)},
    )
    await session.commit()
    return {
        "documento_id": str(doc.id),
        "fotos_incluidas": len(fotos),
        "bucket_uri": uri,
        "status": doc.status.value,
        "revisao": revisao,
    }


async def _finalize_approved_photo_report(
    session: AsyncSession,
    *,
    doc: Documento,
    approval: Aprovacao,
    aprovador: str,
    commit: bool,
) -> dict[str, Any]:
    obra = await _get_obra(session, doc.obra_id)
    periodo_inicio, periodo_fim = _period_from_metadata(doc.metadata_json)
    if not periodo_inicio or not periodo_fim:
        raise ValidationError("Relatório sem período no metadata_json")

    inicio = parse_date(periodo_inicio)
    fim = parse_date(periodo_fim)
    rows = await _load_fotos_with_arquivos(
        session, obra_id=doc.obra_id, inicio=inicio, fim=fim
    )
    fotos = _fotos_to_template_items(rows, embed_images=True)
    html = _render_photo_report_html(
        obra_id=doc.obra_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        revisao=doc.revisao,
        fotos=fotos,
    )
    pdf_bytes = pdf_service.html_to_pdf(html)

    filename = build_photo_report_filename(
        doc.obra_id, periodo_inicio, periodo_fim, doc.revisao, final=True
    )
    final_key = bucket_service.build_documento_key(
        doc.obra_id,
        PHOTO_REPORT_TYPE,
        periodo_inicio,
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
            "tipo": PHOTO_REPORT_TYPE,
            "periodo": [periodo_inicio, periodo_fim],
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
            "fotos_count": len(fotos),
        },
    )
    await audit_service.log_event(
        session,
        entidade="documento",
        entidade_id=str(doc.id),
        acao="relatorio_fotografico_finalizado",
        obra_id=doc.obra_id,
        actor=aprovador,
        detalhes={"bucket_key": final_key, "formato": "pdf", "fotos": len(fotos)},
    )
    if commit:
        await session.commit()
    return {
        "documento_id": str(doc.id),
        "status": doc.status.value,
        "bucket_uri": uri,
        "formato": "pdf",
    }


async def finalize_photo_report(
    session: AsyncSession,
    *,
    documento_id: str,
    aprovador: str,
) -> dict[str, Any]:
    doc = await _get_documento(session, documento_id)
    _require_photo_report_document(doc)
    approval = await _require_approval(session, doc)
    return await _finalize_approved_photo_report(
        session,
        doc=doc,
        approval=approval,
        aprovador=aprovador,
        commit=True,
    )


async def approve_and_finalize_photo_report(
    session: AsyncSession,
    *,
    documento_id: str,
    aprovador: str,
    comentario: str | None = None,
) -> dict[str, Any]:
    doc = await _get_documento(session, documento_id)
    _require_photo_report_document(doc)
    if doc.status == DocumentStatus.FINALIZADO_VALIDADO:
        raise ValidationError("Relatório fotográfico já finalizado")

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
        detalhes={"comentario": comentario, "origem": "relatorio_foto_aprovar_finalizar"},
    )
    await session.flush()

    final = await _finalize_approved_photo_report(
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
