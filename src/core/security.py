from fastapi import Header

from src.config.env import get_settings
from src.core.errors import UnauthorizedError


def verify_openclaw_secret(x_openclaw_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.openclaw_shared_secret:
        return
    if x_openclaw_secret != settings.openclaw_shared_secret:
        raise UnauthorizedError("Shared secret inválido")
