from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DocumentStatus
from src.db.models import Documento, EntradaBruta, Triagem

# "Aguardando aprovação" = documento em rascunho ou em revisão (predicado nomeado,
# usado tanto no dashboard quanto como filtro padrão de pendências de aprovação).
AGUARDANDO_APROVACAO: tuple[DocumentStatus, DocumentStatus] = (
    DocumentStatus.RASCUNHO_GERADO,
    DocumentStatus.EM_REVISAO,
)

PENDING_OBRA_STATUS = "pending_obra"

_MAX_LIMIT = 200


def _clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, _MAX_LIMIT)


async def dashboard_counts(session: AsyncSession) -> dict[str, Any]:
    """Contadores do painel: entradas por status, documentos aguardando aprovação,
    e ``pending_obra`` em aberto."""
    result = await session.execute(
        select(EntradaBruta.status, func.count()).group_by(EntradaBruta.status)
    )
    entradas_por_status = {status: total for status, total in result.all()}

    docs_result = await session.execute(
        select(func.count())
        .select_from(Documento)
        .where(Documento.status.in_(AGUARDANDO_APROVACAO))
    )
    aguardando_aprovacao = docs_result.scalar_one()

    return {
        "entradas_por_status": entradas_por_status,
        "aguardando_aprovacao": aguardando_aprovacao,
        "pending_obra": entradas_por_status.get(PENDING_OBRA_STATUS, 0),
    }


async def list_entradas(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[EntradaBruta]:
    stmt = select(EntradaBruta)
    if status:
        stmt = stmt.where(EntradaBruta.status == status)
    stmt = stmt.order_by(EntradaBruta.created_at.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_entrada(
    session: AsyncSession, entrada_id: uuid.UUID
) -> EntradaBruta | None:
    return await session.get(EntradaBruta, entrada_id)


async def list_documentos(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Documento]:
    stmt = select(Documento)
    if status:
        stmt = stmt.where(Documento.status == status)
    stmt = stmt.order_by(Documento.created_at.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_documento_com_triagem(
    session: AsyncSession, documento_id: uuid.UUID
) -> tuple[Documento, Triagem | None] | None:
    doc = await session.get(Documento, documento_id)
    if doc is None:
        return None
    result = await session.execute(
        select(Triagem)
        .where(Triagem.documento_id == doc.id)
        .order_by(Triagem.created_at.desc())
    )
    triagem = result.scalars().first()
    return doc, triagem
