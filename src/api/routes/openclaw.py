from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.security import verify_openclaw_secret
from src.schemas.domain import OpenClawTelegramPayload
from src.services import ingestao_service

router = APIRouter(prefix="/api/v1/openclaw", tags=["openclaw"])


@router.post("/telegram-event", dependencies=[Depends(verify_openclaw_secret)])
async def telegram_event(
    payload: OpenClawTelegramPayload,
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await ingestao_service.process_telegram_event(session, payload)
