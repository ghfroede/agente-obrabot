from __future__ import annotations

import logging

from redis import Redis

from src.config.env import get_settings
from src.core.errors import RateLimitError

logger = logging.getLogger(__name__)


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def check_openclaw_limits(
    *,
    chat_id: int | None,
    user_id: int | None,
    event_id: str,
) -> None:
    """Token bucket simples via Redis. Desativado quando ``rate_limit_enabled`` é False."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    client = _redis()
    window = settings.rate_limit_window_seconds

    if user_id is not None:
        key = f"rate:openclaw:user:{user_id}"
        count = client.incr(key)
        if count == 1:
            client.expire(key, window)
        if count > settings.rate_limit_user_per_minute:
            logger.warning("rate_limit user_id=%s count=%s", user_id, count)
            raise RateLimitError("Limite de eventos por usuário excedido")

    if chat_id is not None:
        key = f"rate:openclaw:chat:{chat_id}"
        count = client.incr(key)
        if count == 1:
            client.expire(key, window)
        if count > settings.rate_limit_chat_per_minute:
            logger.warning("rate_limit chat_id=%s count=%s", chat_id, count)
            raise RateLimitError("Limite de eventos por grupo excedido")

    event_key = f"rate:openclaw:event:{event_id}"
    if not client.set(event_key, "1", nx=True, ex=window * 10):
        logger.warning("rate_limit duplicate event_id=%s", event_id)
        raise RateLimitError("Evento já recebido recentemente")
