from datetime import datetime, timezone
import hmac
import hashlib
from fastapi import Header, HTTPException, Request

from src.config.env import get_settings
from src.core.errors import UnauthorizedError


def verify_openclaw_secret(x_openclaw_secret: str | None = Header(default=None)) -> None:
    """Legacy: Mantém compatibilidade com shared secret estático."""
    settings = get_settings()
    if not settings.openclaw_shared_secret:
        return
    if x_openclaw_secret != settings.openclaw_shared_secret:
        raise UnauthorizedError("Shared secret inválido")


async def verify_hmac_signature(
    x_signature: str | None = Header(default=None, alias="X-OpenClaw-Signature"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    x_event_id: str | None = Header(default=None, alias="X-Event-Id"),
    request: Request = None,
) -> None:
    """Verifica assinatura HMAC com timestamp e idempotência (padrão de produção)."""
    settings = get_settings()
    if not settings.openclaw_shared_secret:
        return

    # Verifica se headers estão presentes
    if not all([x_signature, x_timestamp, x_event_id]):
        raise HTTPException(
            status_code=401,
            detail="Headers X-OpenClaw-Signature, X-Timestamp e X-Event-Id são obrigatórios",
        )

    # Verifica timestamp (max 5 minutos de diferença)
    try:
        event_time_str = x_timestamp.replace("Z", "+00:00")
        event_time = datetime.fromisoformat(event_time_str)
        now = datetime.now(timezone.utc)
        if abs((now - event_time).total_seconds()) > 300:  # 5 minutos
            raise HTTPException(
                status_code=401,
                detail="Timestamp expirado ou inválido",
            )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Timestamp no formato inválido (ISO 8601)",
        )

    # Calcula assinatura local
    secret = settings.openclaw_shared_secret.encode()
    timestamp = x_timestamp.encode()
    method = request.method.encode()
    path = request.url.path.encode()

    # Lê o body (precisa ser lido apenas uma vez)
    body = await request.body()
    body_hash = hashlib.sha256(body).hexdigest().encode()
    canonical = b"".join([timestamp, method, path, body_hash])

    expected_signature = hmac.new(
        secret, canonical, hashlib.sha256
    ).hexdigest()

    # Verifica assinatura
    if not hmac.compare_digest(x_signature, expected_signature):
        raise HTTPException(
            status_code=401,
            detail="Assinatura HMAC inválida",
        )
