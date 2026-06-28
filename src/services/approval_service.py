from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DocumentStatus
from src.core.errors import NotFoundError
from src.db.models import Aprovacao, Documento
from src.services import audit_service
from src.utils.dates import utc_now


async def _get_documento(session: AsyncSession, documento_id: str | uuid.UUID) -> Documento:
    doc_id = documento_id if isinstance(documento_id, uuid.UUID) else uuid.UUID(str(documento_id))
    result = await session.execute(select(Documento).where(Documento.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError(f"Documento {documento_id} não encontrado")
    return doc


async def approve_document(
    session: AsyncSession,
    *,
    documento_id: str,
    aprovado: bool,
    aprovador: str,
    comentario: str | None = None,
) -> dict[str, Any]:
    doc = await _get_documento(session, documento_id)
    approval = Aprovacao(
        documento_id=doc.id,
        aprovador=aprovador,
        aprovado=aprovado,
        comentario=comentario,
    )
    session.add(approval)
    doc.status = DocumentStatus.APROVADO if aprovado else DocumentStatus.REPROVADO
    doc.updated_at = utc_now()
    await audit_service.log_event(
        session,
        entidade="documento",
        entidade_id=str(doc.id),
        acao="aprovado" if aprovado else "reprovado",
        obra_id=doc.obra_id,
        actor=aprovador,
        detalhes={"comentario": comentario},
    )
    await session.commit()
    return {"documento_id": str(doc.id), "status": doc.status.value, "aprovado": aprovado}
