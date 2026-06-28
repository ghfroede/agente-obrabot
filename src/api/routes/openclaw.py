from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.security import verify_hmac_signature
from src.schemas.domain import OpenClawTelegramPayload
from src.services import ingestao_service

router = APIRouter(prefix="/api/v1/openclaw", tags=["openclaw"])

@router.post("/telegram-event", dependencies=[Depends(verify_hmac_signature)])
async def telegram_event(
    request: Request,
    payload: OpenClawTelegramPayload,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Recebe eventos do OpenClaw com HMAC + timestamp + event_id."""
    return await ingestao_service.process_telegram_event(
        session, payload, request.headers
    )
