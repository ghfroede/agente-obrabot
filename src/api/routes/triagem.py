import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.db.models import Triagem
from src.schemas.domain import TriagemOutput
from src.services import openai_service

router = APIRouter(prefix="/api/v1/triagem", tags=["triagem"])


@router.post("/classificar", response_model=TriagemOutput)
async def classificar(payload: dict) -> TriagemOutput:
    text = str(payload.get("texto", ""))
    context = payload.get("contexto")
    return await openai_service.triagem_structured(text, context=context)


@router.get("/{triagem_id}")
async def obter_triagem(
    triagem_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict:
    result = await session.execute(select(Triagem).where(Triagem.id == triagem_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Triagem não encontrada")
    return {
        "id": str(row.id),
        "obra_id": row.obra_id,
        "tipo_documento": row.tipo_documento,
        "confianca": row.confianca,
        "resumo": row.resumo,
        "campos_extraidos": row.campos_extraidos,
        "acao_sugerida": row.acao_sugerida,
        "precisa_aprovacao": row.precisa_aprovacao,
        "documento_id": str(row.documento_id) if row.documento_id else None,
    }
