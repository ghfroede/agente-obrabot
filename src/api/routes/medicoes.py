from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.errors import NotFoundError, ValidationError
from src.schemas.domain import MedicaoPeriodoCloseRequest, MedicaoRegistroRequest
from src.services import medicao_service

router = APIRouter(prefix="/api/v1/medicoes", tags=["medicoes"])


@router.post("")
async def registrar_medicoes(
    body: MedicaoRegistroRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await medicao_service.registrar_medicao(
            session,
            obra_id=body.obra_id,
            periodo_ref=body.periodo_ref,
            itens=[item.model_dump() for item in body.itens],
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fechar")
async def fechar_periodo_medicao(
    body: MedicaoPeriodoCloseRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await medicao_service.fechar_periodo(
            session,
            obra_id=body.obra_id,
            periodo_ref=body.periodo_ref,
            aprovador=body.aprovador,
            comentario=body.comentario,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
