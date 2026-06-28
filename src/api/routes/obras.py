from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.db.models import Obra
from src.services import ingestao_service

router = APIRouter(prefix="/api/v1/obras", tags=["obras"])


@router.get("")
async def listar_obras(session: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await session.execute(select(Obra).order_by(Obra.created_at.desc()))
    return [
        {"id": o.id, "nome": o.nome, "slug": o.slug, "status": o.status}
        for o in result.scalars().all()
    ]


@router.post("")
async def criar_obra(payload: dict, session: AsyncSession = Depends(get_db)) -> dict:
    obra_id = str(payload.get("id", "")).strip()
    nome = str(payload.get("nome", obra_id)).strip()
    if not obra_id:
        raise HTTPException(status_code=400, detail="id é obrigatório")
    obra = await ingestao_service.ensure_obra(session, obra_id, nome)
    await session.commit()
    return {"id": obra.id, "nome": obra.nome, "slug": obra.slug, "status": obra.status}
