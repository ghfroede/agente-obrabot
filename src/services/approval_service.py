from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DocumentStatus
from src.db.models import Aprovacao
from src.services import audit_service
from src.services import common as service_common
from src.utils.dates import utc_now


async def approve_document(
    session: AsyncSession,
    *,
    documento_id: str,
    aprovado: bool,
    aprovador: str,
    comentario: str | None = None,
) -> dict[str, Any]:
    doc = await service_common.get_documento(session, documento_id)
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
