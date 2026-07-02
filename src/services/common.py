from __future__ import annotations

import uuid

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import DocumentStatus
from src.core.errors import ApprovalRequiredError, NotFoundError
from src.db.models import Aprovacao, Documento, Obra


def jinja_env() -> Environment:
    settings = get_settings()
    return Environment(
        loader=FileSystemLoader(settings.templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )


async def get_obra(session: AsyncSession, obra_id: str) -> Obra:
    obra = await session.get(Obra, obra_id)
    if obra is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    return obra


async def get_documento(session: AsyncSession, documento_id: str | uuid.UUID) -> Documento:
    doc_id = documento_id if isinstance(documento_id, uuid.UUID) else uuid.UUID(str(documento_id))
    result = await session.execute(select(Documento).where(Documento.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError(f"Documento {documento_id} não encontrado")
    return doc


async def require_approval(session: AsyncSession, doc: Documento) -> Aprovacao:
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
