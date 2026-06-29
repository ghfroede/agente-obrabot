from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.schemas.domain import ResolveEntradaObraRequest
from src.services import entrada_service

router = APIRouter(prefix="/api/v1/entradas", tags=["entradas"])


@router.post("/{entrada_id}/resolver-obra")
async def resolver_obra(
    entrada_id: uuid.UUID,
    body: ResolveEntradaObraRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await entrada_service.resolve_pending_obra(
        session, entrada_id=entrada_id, obra_id=body.obra_id
    )
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="EntradaBruta não encontrada")
    if result["status"] == "obra_not_found":
        raise HTTPException(status_code=404, detail=f"Obra {body.obra_id} não encontrada")
    return result
