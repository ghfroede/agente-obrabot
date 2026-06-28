import hashlib
import hmac
import json
from datetime import UTC, datetime

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
    *,
    request: Request,
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
    # Após o check acima, os três headers e o request são não-nulos (narrowing p/ mypy).
    assert x_signature is not None
    assert x_timestamp is not None
    assert x_event_id is not None

    # Verifica timestamp (max 5 minutos de diferença)
    try:
        event_time_str = x_timestamp.replace("Z", "+00:00")
        event_time = datetime.fromisoformat(event_time_str)
        now = datetime.now(UTC)
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

    # Lê o body (precisa ser lido apenas uma vez)
    body = await request.body()

    # Valida que o X-Event-Id do header bate com o event_id do payload (prova ligada ao conteúdo)
    try:
        payload_event_id = json.loads(body).get("event_id")
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Body inválido (JSON esperado)")
    if payload_event_id != x_event_id:
        raise HTTPException(
            status_code=401,
            detail="X-Event-Id não corresponde ao event_id do payload",
        )

    # Calcula assinatura local — event_id participa do material assinado
    secret = settings.openclaw_shared_secret.encode()
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        [x_timestamp, x_event_id, request.method, request.url.path, body_hash]
    ).encode()

    expected_signature = hmac.new(secret, canonical, hashlib.sha256).hexdigest()

    # Verifica assinatura
    if not hmac.compare_digest(x_signature, expected_signature):
        raise HTTPException(
            status_code=401,
            detail="Assinatura HMAC inválida",
        )
