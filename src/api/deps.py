import hmac
from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.db.client import get_async_session
from src.services import rate_limit_service


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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OBRABOT_API_KEY obrigatório para rotas protegidas",
        )
    if x_obrabot_api_key is None or not hmac.compare_digest(x_obrabot_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente",
        )
    client_ip = request.client.host if request.client else "desconhecido"
    rate_limit_service.check_protected_route_limit(
        api_key=x_obrabot_api_key,
        ip=client_ip,
        method=request.method,
        path=request.url.path,
    )


DbSession = Depends(get_db)
ApiKeyDep = Depends(require_api_key)
