from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

from src.config.env import get_settings
from src.core.errors import ForbiddenError, UnauthorizedError
from src.schemas.domain import OpenClawTelegramPayload
from src.services import rate_limit_service

logger = logging.getLogger(__name__)


def _header(request: Request, *names: str) -> str | None:
    for name in names:
        value = request.headers.get(name)
        if value:
            return value
    return None


def _ensure_secret_configured() -> None:
    settings = get_settings()
    hmac_required = settings.is_production or settings.openclaw_require_hmac
    if hmac_required and not settings.openclaw_shared_secret:
        raise HTTPException(
            status_code=500,
            detail="OPENCLAW_SHARED_SECRET obrigatório quando HMAC é obrigatório",
        )
    if not settings.openclaw_shared_secret and not settings.is_production:
        logger.warning(
            "OPENCLAW_SHARED_SECRET vazio — webhook sem autenticação (apenas desenvolvimento)"
        )


def _parse_timestamp(value: str, max_skew: int) -> None:
    try:
        event_time = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=401, detail="Timestamp no formato inválido (ISO 8601)")
    now = datetime.now(UTC)
    if abs((now - event_time).total_seconds()) > max_skew:
        raise HTTPException(status_code=401, detail="Timestamp expirado ou inválido")


def _verify_hmac(
    *,
    secret: str,
    timestamp: str,
    event_id: str,
    method: str,
    path: str,
    body: bytes,
    signature: str,
) -> None:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([timestamp, event_id, method, path, body_hash]).encode()
    expected = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Assinatura HMAC inválida")


def validate_telegram_allowlist(payload: OpenClawTelegramPayload) -> None:
    settings = get_settings()
    tg = payload.telegram

    if settings.allowed_chat_ids and str(tg.chat.id) not in settings.allowed_chat_ids:
        raise ForbiddenError(f"Chat {tg.chat.id} não autorizado")

    if tg.from_user and settings.allowed_user_ids:
        if str(tg.from_user.id) not in settings.allowed_user_ids:
            raise ForbiddenError(f"Usuário {tg.from_user.id} não autorizado")

    thread_id = tg.message_thread_id
    if thread_id is not None and settings.allowed_thread_ids:
        if str(thread_id) not in settings.allowed_thread_ids:
            raise ForbiddenError(f"Thread {thread_id} não autorizada")


async def verify_openclaw_webhook(request: Request) -> bytes:
    """Valida autenticação, tamanho do body e HMAC. Retorna o body para reuso."""
    settings = get_settings()
    _ensure_secret_configured()

    body = await request.body()
    if len(body) > settings.webhook_max_body_bytes:
        raise HTTPException(status_code=413, detail="Payload excede WEBHOOK_MAX_BODY_BYTES")

    signature = _header(request, "X-OpenClaw-Signature")
    timestamp = _header(request, "X-OpenClaw-Timestamp", "X-Timestamp")
    event_id = _header(request, "X-OpenClaw-Event-Id", "X-Event-Id")
    static_secret = _header(request, "X-OpenClaw-Secret")

    secret = settings.openclaw_shared_secret
    require_hmac = settings.openclaw_require_hmac or settings.is_production

    if not secret:
        return body

    if not require_hmac and static_secret and hmac.compare_digest(static_secret, secret):
        return body

    if require_hmac or signature:
        if not all([signature, timestamp, event_id]):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Headers X-OpenClaw-Signature, X-OpenClaw-Timestamp e "
                    "X-OpenClaw-Event-Id são obrigatórios"
                ),
            )

        assert signature is not None and timestamp is not None and event_id is not None

        _parse_timestamp(timestamp, settings.openclaw_max_clock_skew_seconds)

        try:
            payload_data: dict[str, Any] = json.loads(body)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=401, detail="Body inválido (JSON esperado)")
        if payload_data.get("event_id") != event_id:
            raise HTTPException(
                status_code=401,
                detail="X-OpenClaw-Event-Id não corresponde ao event_id do payload",
            )

        _verify_hmac(
            secret=secret,
            timestamp=timestamp,
            event_id=event_id,
            method=request.method,
            path=request.url.path,
            body=body,
            signature=signature,
        )

        telegram = payload_data.get("telegram") or {}
        chat = telegram.get("chat") or {}
        from_user = telegram.get("from") or {}
        rate_limit_service.check_openclaw_limits(
            chat_id=chat.get("id"),
            user_id=from_user.get("id"),
            event_id=event_id,
        )

    return body


def verify_openclaw_secret(x_openclaw_secret: str | None = None) -> None:
    settings = get_settings()
    if settings.is_production and not settings.openclaw_shared_secret:
        raise UnauthorizedError("OPENCLAW_SHARED_SECRET obrigatório em produção")
    if not settings.openclaw_shared_secret:
        return
    if x_openclaw_secret != settings.openclaw_shared_secret:
        raise UnauthorizedError("Shared secret inválido")


async def verify_hmac_signature(
    request: Request,
    x_signature: str | None = None,
    x_timestamp: str | None = None,
    x_event_id: str | None = None,
) -> None:
    """Compat: delega para verify_openclaw_webhook."""
    await verify_openclaw_webhook(request)
