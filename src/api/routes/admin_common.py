from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from src.config.env import get_settings

templates = Jinja2Templates(directory=get_settings().templates_dir)

ENTRADA_STATUSES: tuple[str, ...] = (
    "received",
    "processing",
    "completed",
    "failed",
    "pending_obra",
)


def effective_admin_password() -> str:
    settings = get_settings()
    if settings.admin_password:
        return settings.admin_password
    if not settings.is_production:
        return settings.obrabot_api_key
    return ""


def require_admin_session(request: Request) -> None:
    if not request.session.get("admin"):
        from src.core.errors import AdminLoginRequired

        raise AdminLoginRequired()


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def origin_parts(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    return scheme, host, parsed.port


def default_port(scheme: str) -> int | None:
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return None


def effective_port(scheme: str, port: int | None) -> int | None:
    return port if port is not None else default_port(scheme)


def check_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if origin is None and referer is None:
        if get_settings().is_production:
            raise HTTPException(status_code=403, detail="Origem não verificada")
        return
    source = origin or referer
    if source is None:
        raise HTTPException(status_code=403, detail="Origem não autorizada")

    base_scheme, base_host, base_port = origin_parts(str(request.base_url))
    source_scheme, source_host, source_port = origin_parts(source)
    if source_scheme != base_scheme or source_host != base_host:
        raise HTTPException(status_code=403, detail="Origem não autorizada")
    if effective_port(source_scheme, source_port) != effective_port(base_scheme, base_port):
        raise HTTPException(status_code=403, detail="Origem não autorizada")


def as_textarea_lines(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def rdo_campos_form(documento: object) -> dict[str, str]:
    metadata_raw = getattr(documento, "metadata_json", None)
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    conteudo_raw = metadata.get("conteudo")
    conteudo = conteudo_raw if isinstance(conteudo_raw, dict) else {}
    fields_raw = metadata.get("campos_editaveis") or conteudo.get("campos_editaveis")
    fields = fields_raw if isinstance(fields_raw, dict) else {}
    return {
        "clima": as_textarea_lines(fields.get("clima")),
        "equipe": as_textarea_lines(fields.get("equipe")),
        "equipamentos": as_textarea_lines(fields.get("equipamentos")),
        "observacoes": as_textarea_lines(fields.get("observacoes")),
        "complementos_engenheiro": as_textarea_lines(fields.get("complementos_engenheiro")),
    }
