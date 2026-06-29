from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.schemas.obras import ObraCreate, ObraResponse
from src.services import obra_service

router = APIRouter(prefix="/api/v1/obras", tags=["obras"])


@router.get("", response_model=list[ObraResponse])
async def listar_obras(session: AsyncSession = Depends(get_db)) -> list[ObraResponse]:
    obras = await obra_service.list_obras(session)
    return [ObraResponse.model_validate(obra) for obra in obras]


@router.post("", response_model=ObraResponse)
async def criar_obra(
    payload: ObraCreate, session: AsyncSession = Depends(get_db)
) -> ObraResponse:
    obra = await obra_service.upsert_obra(session, payload)
    await session.commit()
    return ObraResponse.model_validate(obra)
