from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.security import validate_telegram_allowlist, verify_openclaw_webhook
from src.schemas.domain import OpenClawTelegramPayload
from src.services import entrada_service

router = APIRouter(prefix="/api/v1/openclaw", tags=["openclaw"])


@router.post(
    "/telegram-event",
    status_code=202,
    dependencies=[Depends(verify_openclaw_webhook)],
)
async def telegram_event(
    payload: OpenClawTelegramPayload,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Recebe evento OpenClaw (HMAC/allowlist/idempotência), grava EntradaBruta e enfileira."""
    validate_telegram_allowlist(payload)
    return await entrada_service.ingest_telegram(session, payload)
