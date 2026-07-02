import hmac
import logging
from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.db.client import get_async_session
from src.services import rate_limit_service

logger = logging.getLogger(__name__)

_CONFIG_ERROR_DETAIL = "Configuração do servidor incompleta"


def client_ip(request: Request) -> str:
    """IP do cliente; atrás de proxy (Railway) usa o primeiro hop de X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "desconhecido"


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_async_session():
        yield session


async def require_api_key(
    request: Request,
    x_obrabot_api_key: str | None = Header(default=None, alias="X-Obrabot-API-Key"),
) -> None:
    settings = get_settings()
    expected = settings.obrabot_api_key
    if not expected:
        logger.error("OBRABOT_API_KEY ausente para rotas protegidas")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_CONFIG_ERROR_DETAIL,
        )
    if x_obrabot_api_key is None or not hmac.compare_digest(x_obrabot_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente",
        )
    rate_limit_service.check_protected_route_limit(
        api_key=x_obrabot_api_key,
        ip=client_ip(request),
        method=request.method,
        path=request.url.path,
    )
