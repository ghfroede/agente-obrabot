from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.db.client import get_async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, str] = {"app": "ok"}

    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"

    try:
        redis = Redis.from_url(settings.redis_url)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    healthy = all(v == "ok" for v in checks.values())
    response.status_code = 200 if healthy else 503
    return {"status": "healthy" if healthy else "degraded", "checks": checks}
