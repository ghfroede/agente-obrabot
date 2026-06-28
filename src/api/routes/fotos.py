from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.schemas.domain import FotoRelatorioRequest
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
