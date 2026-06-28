from __future__ import annotations

from datetime import date
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import GENERATED_BY, DocumentStatus
from src.db.models import Documento, Foto
from src.services import audit_service, bucket_service
from src.utils.dates import parse_date
from src.utils.filenames import build_photo_report_filename, next_revision
from src.utils.hashing import sha256_hex


def _jinja_env() -> Environment:
    settings = get_settings()
    return Environment(
        loader=FileSystemLoader(settings.templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
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
    query = select(Foto).where(Foto.obra_id == obra_id)
    if inicio and fim:
        query = query.where(
            and_(Foto.data_foto >= inicio, Foto.data_foto <= fim)
        )
    result = await session.execute(query.order_by(Foto.data_foto.asc()))
    fotos = list(result.scalars().all())

    existing = await session.execute(
        select(Documento.revisao).where(
            Documento.obra_id == obra_id,
            Documento.tipo == "relatorio_fotografico",
        )
    )
    revisao = next_revision(list(existing.scalars().all()))

    env = _jinja_env()
    template = env.get_template("relatorio_fotografico.html")
    html = template.render(
        obra_id=obra_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        revisao=revisao,
        fotos=fotos,
        generated_by=GENERATED_BY,
    )
    filename = build_photo_report_filename(
        obra_id, periodo_inicio, periodo_fim, revisao, final=False
    )
    html_name = filename.replace(".pdf", ".html")
    key = bucket_service.build_documento_key(
        obra_id, "relatorio_fotografico", periodo_inicio, revisao, html_name, draft=True
    )
    body = html.encode("utf-8")
    uri = bucket_service.put_bytes(key, body, content_type="text/html")
    file_hash = sha256_hex(body)

    doc = Documento(
        obra_id=obra_id,
        tipo="relatorio_fotografico",
        titulo=f"Relatório fotográfico {periodo_inicio} a {periodo_fim}",
        data_ref=inicio or date.today(),
        revisao=revisao,
        status=DocumentStatus.RASCUNHO_GERADO,
        bucket_key=key,
        bucket_uri=uri,
        hash_sha256=file_hash,
        metadata_json={"fotos_count": len(fotos), "periodo": [periodo_inicio, periodo_fim]},
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
    }
