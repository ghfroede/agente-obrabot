from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Obra
from src.schemas.obras import ObraCreate
from src.utils.filenames import obra_slug


async def list_obras(session: AsyncSession, *, only_active: bool = False) -> list[Obra]:
    stmt = select(Obra)
    if only_active:
        stmt = stmt.where(Obra.status == "ativa")
    result = await session.execute(stmt.order_by(Obra.id.asc()))
    return list(result.scalars().all())


async def upsert_obra(session: AsyncSession, payload: ObraCreate) -> Obra:
    obra = await session.get(Obra, payload.id)
    if obra is None:
        obra = Obra(
            id=payload.id,
            nome=payload.nome,
            slug=obra_slug(payload.nome),
            status=payload.status,
            metadata_json=payload.metadata_json,
        )
        session.add(obra)
        await session.flush()
        return obra

    obra.nome = payload.nome
    obra.slug = obra_slug(payload.nome)
    obra.status = payload.status
    obra.metadata_json = payload.metadata_json
    await session.flush()
    return obra


async def active_obras_summary(session: AsyncSession) -> list[dict[str, str]]:
    obras = await list_obras(session, only_active=True)
    return [{"id": obra.id, "nome": obra.nome, "status": obra.status} for obra in obras]
