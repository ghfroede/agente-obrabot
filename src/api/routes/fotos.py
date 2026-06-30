from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.errors import NotFoundError, ValidationError
from src.schemas.domain import FotoRelatorioApproveFinalizeRequest, FotoRelatorioRequest
from src.services import foto_service

router = APIRouter(prefix="/api/v1/fotos", tags=["fotos"])


@router.post("/relatorio")
async def gerar_relatorio(
    body: FotoRelatorioRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await foto_service.generate_photo_report(
        session,
        obra_id=body.obra_id,
        periodo_inicio=body.periodo_inicio,
        periodo_fim=body.periodo_fim,
    )


@router.post("/relatorio/aprovar-finalizar")
async def relatorio_aprovar_finalizar(
    body: FotoRelatorioApproveFinalizeRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await foto_service.approve_and_finalize_photo_report(
            session,
            documento_id=body.documento_id,
            aprovador=body.aprovador,
            comentario=body.comentario,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
