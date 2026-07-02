from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request

from src.api.deps import client_ip
from src.api.routes.admin_common import (
    check_same_origin,
    effective_admin_password,
    templates,
)
from src.core.errors import RateLimitError
from src.services import rate_limit_service

logger = logging.getLogger(__name__)
_CONFIG_ERROR_DETAIL = "Configuração do servidor incompleta"

router = APIRouter()


@router.get("/login")
async def login_form(request: Request) -> Any:
    return templates.TemplateResponse(request, "admin/login.html", {"erro": None})


@router.post("/login")
async def login_submit(request: Request, senha: str = Form(...)) -> Any:
    from fastapi.responses import RedirectResponse

    check_same_origin(request)
    senha_efetiva = effective_admin_password()
    if not senha_efetiva:
        logger.error("ADMIN_PASSWORD/OBRABOT_API_KEY ausente para o painel admin")
        raise HTTPException(
            status_code=500,
            detail=_CONFIG_ERROR_DETAIL,
        )

    try:
        rate_limit_service.check_admin_login_limit(ip=client_ip(request))
    except RateLimitError:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"erro": "Muitas tentativas. Aguarde um instante e tente novamente."},
            status_code=429,
        )

    if not hmac.compare_digest(senha, senha_efetiva):
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"erro": "Senha inválida."},
            status_code=200,
        )

    request.session["admin"] = True
    return RedirectResponse("/admin", status_code=303)


@router.post("/logout")
async def logout(request: Request) -> Any:
    from fastapi.responses import RedirectResponse

    check_same_origin(request)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
