from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.schemas.telegram_contextos import (
    TelegramContextoCreate,
    TelegramContextoResponse,
)
from src.services import telegram_context_service

router = APIRouter(prefix="/api/v1/telegram-contextos", tags=["telegram-contextos"])


@router.get("", response_model=list[TelegramContextoResponse])
async def listar_contextos(
    session: AsyncSession = Depends(get_db),
) -> list[TelegramContextoResponse]:
    rows = await telegram_context_service.list_contextos(session)
    return [TelegramContextoResponse.model_validate(row) for row in rows]


@router.post("", response_model=TelegramContextoResponse)
async def criar_contexto(
    payload: TelegramContextoCreate,
    session: AsyncSession = Depends(get_db),
) -> TelegramContextoResponse:
    row = await telegram_context_service.upsert_contexto(session, payload)
    await session.commit()
    return TelegramContextoResponse.model_validate(row)
