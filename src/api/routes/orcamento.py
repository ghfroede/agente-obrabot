from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.errors import NotFoundError, ValidationError
from src.schemas.domain import (
    BaselineApproveRequest,
    BaselineValidateRequest,
    CronogramaImportRequest,
    OrcamentoImportRequest,
)
from src.services import orcamento_service

router = APIRouter(prefix="/api/v1", tags=["orcamento", "cronograma", "baseline"])


@router.get("/orcamento/{obra_id}")
async def listar_orcamento(
    obra_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await orcamento_service.list_orcamento(session, obra_id=obra_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/orcamento/importar")
async def importar_orcamento(
    body: OrcamentoImportRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await orcamento_service.import_orcamento(
            session, obra_id=body.obra_id, itens=body.itens
        )
    except (NotFoundError, ValidationError) as exc:
        status = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/cronograma/{obra_id}")
async def listar_cronograma(
    obra_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await orcamento_service.list_cronograma(session, obra_id=obra_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/cronograma/importar")
async def importar_cronograma(
    body: CronogramaImportRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await orcamento_service.import_cronograma(
            session, obra_id=body.obra_id, atividades=body.atividades
        )
    except (NotFoundError, ValidationError) as exc:
        status = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/baseline/validar")
async def validar_baseline(
    body: BaselineValidateRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await orcamento_service.validate_baseline(session, obra_id=body.obra_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/baseline/aprovar")
async def aprovar_baseline(
    body: BaselineApproveRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await orcamento_service.approve_baseline(
            session,
            obra_id=body.obra_id,
            aprovador=body.aprovador,
            comentario=body.comentario,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
