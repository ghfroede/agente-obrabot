from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.security import verify_hmac_signature
from src.schemas.domain import OpenClawTelegramPayload
from src.services import entrada_service

router = APIRouter(prefix="/api/v1/openclaw", tags=["openclaw"])


@router.post(
    "/telegram-event",
    status_code=202,
    dependencies=[Depends(verify_hmac_signature)],
)
async def telegram_event(
    payload: OpenClawTelegramPayload,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Recebe evento OpenClaw (HMAC/timestamp/event_id), grava EntradaBruta e enfileira (202)."""
    return await entrada_service.ingest_telegram(session, payload)
