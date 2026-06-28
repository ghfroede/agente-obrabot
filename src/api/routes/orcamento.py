from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.schemas.domain import CronogramaImportRequest, OrcamentoImportRequest
from src.services import orcamento_service

router = APIRouter(prefix="/api/v1", tags=["orcamento", "cronograma"])


@router.post("/orcamento/importar")
async def importar_orcamento(
    body: OrcamentoImportRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await orcamento_service.import_orcamento(
        session, obra_id=body.obra_id, itens=body.itens
    )


@router.post("/cronograma/importar")
async def importar_cronograma(
    body: CronogramaImportRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await orcamento_service.import_cronograma(
        session, obra_id=body.obra_id, atividades=body.atividades
    )
