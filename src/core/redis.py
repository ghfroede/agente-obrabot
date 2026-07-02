from __future__ import annotations

from functools import lru_cache

from redis import Redis

from src.config.env import get_settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    """Conexão Redis síncrona compartilhada (RQ, rate-limit, health)."""
    return Redis.from_url(get_settings().redis_url)
