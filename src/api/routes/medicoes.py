from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.services import medicao_service

router = APIRouter(prefix="/api/v1/medicoes", tags=["medicoes"])


@router.post("")
async def registrar_medicoes(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await medicao_service.registrar_medicao(
        session,
        obra_id=str(payload["obra_id"]),
        periodo_ref=str(payload["periodo_ref"]),
        itens=list(payload.get("itens", [])),
    )
