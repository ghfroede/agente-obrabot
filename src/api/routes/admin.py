from __future__ import annotations

import hmac
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config.env import get_settings
from src.core.constants import DocumentStatus
from src.core.errors import AdminLoginRequired, NotFoundError, RateLimitError
from src.db.models import Obra
from src.schemas.obras import ObraCreate
from src.services import (
    admin_service,
    approval_service,
    entrada_service,
    obra_service,
    rate_limit_service,
)

router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory=get_settings().templates_dir)

# Status válidos de EntradaBruta (NÃO inclui "queued" — não é status de EntradaBruta).
ENTRADA_STATUSES: tuple[str, ...] = (
    "received",
    "processing",
    "completed",
    "failed",
    "pending_obra",
)

DOCUMENTO_STATUSES: tuple[str, ...] = tuple(s.value for s in DocumentStatus)


def effective_admin_password() -> str:
    settings = get_settings()
    if settings.admin_password:
        return settings.admin_password
    if not settings.is_production:
        return settings.obrabot_api_key
    return ""


def require_admin_session(request: Request) -> None:
    """Guard de sessão. RAISE (nunca return) — um Depends que retorna Response não
    interrompe a rota; o handler de ``AdminLoginRequired`` redireciona para o login."""
    if not request.session.get("admin"):
        raise AdminLoginRequired()


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _check_same_origin(request: Request) -> None:
    """Defesa-em-profundidade CSRF: POST exige Origin/Referer same-origin.

    Em produção, ausência total de Origin e Referer é bloqueada (fail-closed).
    Em dev, mantém-se permissivo para facilitar testes manuais.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if origin is None and referer is None:
        if get_settings().is_production:
            raise HTTPException(status_code=403, detail="Origem não verificada")
        return
    source = origin or referer
    base = str(request.base_url).rstrip("/")
    if source is None or not source.startswith(base):
        raise HTTPException(status_code=403, detail="Origem não autorizada")


# ---------------------------------------------------------------------------
# Login / logout (sem guard de sessão)
# ---------------------------------------------------------------------------


@router.get("/login")
async def login_form(request: Request) -> Any:
    return templates.TemplateResponse(request, "admin/login.html", {"erro": None})


@router.post("/login")
async def login_submit(request: Request, senha: str = Form(...)) -> Any:
    senha_efetiva = effective_admin_password()
    # Checagem de config ANTES de compare_digest — compare_digest(x, "") seria False
    # e mascararia o 500 como falha de senha.
    if not senha_efetiva:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD/OBRABOT_API_KEY obrigatória para o painel admin",
        )

    client_ip = request.client.host if request.client else "desconhecido"
    try:
        rate_limit_service.check_admin_login_limit(ip=client_ip)
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
    _check_same_origin(request)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("", dependencies=[Depends(require_admin_session)])
async def dashboard(request: Request, session: AsyncSession = Depends(get_db)) -> Any:
    counts = await admin_service.dashboard_counts(session)
    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"counts": counts}
    )


# ---------------------------------------------------------------------------
# Obras
# ---------------------------------------------------------------------------


@router.get("/obras", dependencies=[Depends(require_admin_session)])
async def obras_list(request: Request, session: AsyncSession = Depends(get_db)) -> Any:
    obras = await obra_service.list_obras(session)
    return templates.TemplateResponse(
        request, "admin/obras.html", {"obras": obras}
    )


@router.get("/obras/nova", dependencies=[Depends(require_admin_session)])
async def obra_nova_form(request: Request) -> Any:
    return templates.TemplateResponse(
        request,
        "admin/obra_form.html",
        {"obra": None, "editar": False, "erro": None},
    )


@router.post("/obras/nova", dependencies=[Depends(require_admin_session)])
async def obra_nova_submit(
    request: Request,
    id: str = Form(...),
    nome: str = Form(...),
    status: str = Form("ativa"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    _check_same_origin(request)
    try:
        payload = ObraCreate(id=id, nome=nome, status=status)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin/obra_form.html",
            {"obra": None, "editar": False, "erro": str(exc)},
            status_code=200,
        )
    await obra_service.upsert_obra(session, payload)
    await session.commit()
    return RedirectResponse("/admin/obras", status_code=303)


@router.get("/obras/{obra_id}/editar", dependencies=[Depends(require_admin_session)])
async def obra_editar_form(
    obra_id: str, request: Request, session: AsyncSession = Depends(get_db)
) -> Any:
    obras = await obra_service.list_obras(session)
    obra = next((o for o in obras if o.id == obra_id), None)
    if obra is None:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    return templates.TemplateResponse(
        request,
        "admin/obra_form.html",
        {"obra": obra, "editar": True, "erro": None},
    )


@router.post("/obras/{obra_id}/editar", dependencies=[Depends(require_admin_session)])
async def obra_editar_submit(
    obra_id: str,
    request: Request,
    nome: str = Form(...),
    status: str = Form("ativa"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    _check_same_origin(request)
    # id é read-only no editar — editar exige obra existente; senão upsert criaria nova.
    existing = await session.get(Obra, obra_id)
    if existing is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    payload = ObraCreate(id=obra_id, nome=nome, status=status)
    await obra_service.upsert_obra(session, payload)
    await session.commit()
    return RedirectResponse("/admin/obras", status_code=303)


@router.post("/obras/{obra_id}/status", dependencies=[Depends(require_admin_session)])
async def obra_toggle_status(
    obra_id: str, request: Request, session: AsyncSession = Depends(get_db)
) -> Any:
    _check_same_origin(request)
    obra = await session.get(Obra, obra_id)
    if obra is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    novo_status = "inativa" if obra.status == "ativa" else "ativa"
    obra = await obra_service.set_status(session, obra_id, novo_status)
    await session.commit()
    return templates.TemplateResponse(
        request, "admin/_obra_row.html", {"obra": obra}
    )


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


@router.get("/entradas", dependencies=[Depends(require_admin_session)])
async def entradas_list(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> Any:
    erro: str | None = None
    status_filtro: str | None = None
    if status:
        if status in ENTRADA_STATUSES:
            status_filtro = status
        else:
            erro = f"Status '{status}' inválido para entradas."
    entradas = await admin_service.list_entradas(
        session, status=status_filtro, limit=limit, offset=offset
    )
    ctx: dict[str, Any] = {
        "entradas": entradas,
        "statuses": ENTRADA_STATUSES,
        "status_atual": status_filtro,
        "erro": erro,
        "limit": limit,
        "offset": offset,
    }
    template = "admin/_entradas_table.html" if _is_htmx(request) else "admin/entradas.html"
    return templates.TemplateResponse(request, template, ctx)


@router.get("/entradas/{entrada_id}", dependencies=[Depends(require_admin_session)])
async def entrada_detail(
    entrada_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_db)
) -> Any:
    entrada = await admin_service.get_entrada(session, entrada_id)
    if entrada is None:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    raw_json = json.dumps(entrada.raw_payload or {}, indent=2, ensure_ascii=False)
    obras = await obra_service.active_obras_summary(session)
    return templates.TemplateResponse(
        request,
        "admin/entrada_detail.html",
        {
            "entrada": entrada,
            "raw_json": raw_json,
            "obras": obras,
            "is_pending": entrada.status == entrada_service.PENDING_OBRA_STATUS,
        },
    )


@router.post(
    "/entradas/{entrada_id}/resolver-obra",
    dependencies=[Depends(require_admin_session)],
)
async def entrada_resolver_obra(
    entrada_id: uuid.UUID,
    request: Request,
    obra_id: str = Form(...),
    session: AsyncSession = Depends(get_db),
) -> Any:
    _check_same_origin(request)
    # resolve_pending_obra commita internamente — a rota NÃO commita.
    result = await entrada_service.resolve_pending_obra(
        session, entrada_id=entrada_id, obra_id=obra_id
    )
    erro: str | None = None
    if result["status"] == "not_found":
        erro = "Entrada não encontrada."
    elif result["status"] == "obra_not_found":
        erro = f"Obra {obra_id} não encontrada."
    sucesso = result["status"] == "queued"
    return templates.TemplateResponse(
        request,
        "admin/_entrada_resolver.html",
        {
            "entrada_id": str(entrada_id),
            "result": result,
            "erro": erro,
            "sucesso": sucesso,
        },
    )


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------


@router.get("/documentos", dependencies=[Depends(require_admin_session)])
async def documentos_list(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> Any:
    erro: str | None = None
    status_filtro: str | None = None
    if status:
        if status in DOCUMENTO_STATUSES:
            status_filtro = status
        else:
            erro = f"Status '{status}' inválido para documentos."
    documentos = await admin_service.list_documentos(
        session, status=status_filtro, limit=limit, offset=offset
    )
    ctx: dict[str, Any] = {
        "documentos": documentos,
        "statuses": DOCUMENTO_STATUSES,
        "status_atual": status_filtro,
        "erro": erro,
        "limit": limit,
        "offset": offset,
    }
    template = (
        "admin/_documentos_table.html" if _is_htmx(request) else "admin/documentos.html"
    )
    return templates.TemplateResponse(request, template, ctx)


@router.get("/documentos/{documento_id}", dependencies=[Depends(require_admin_session)])
async def documento_detail(
    documento_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_db)
) -> Any:
    found = await admin_service.get_documento_com_triagem(session, documento_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    doc, triagem = found
    return templates.TemplateResponse(
        request,
        "admin/documento_detail.html",
        {
            "documento": doc,
            "triagem": triagem,
            "aguardando_aprovacao": doc.status in admin_service.AGUARDANDO_APROVACAO,
        },
    )


@router.post(
    "/documentos/{documento_id}/aprovar",
    dependencies=[Depends(require_admin_session)],
)
async def documento_aprovar(
    documento_id: uuid.UUID,
    request: Request,
    aprovado: bool = Form(...),
    aprovador: str = Form("engenheiro"),
    comentario: str | None = Form(default=None),
    session: AsyncSession = Depends(get_db),
) -> Any:
    _check_same_origin(request)
    # approve_document commita internamente — a rota NÃO commita.
    try:
        result = await approval_service.approve_document(
            session,
            documento_id=str(documento_id),
            aprovado=aprovado,
            aprovador=aprovador,
            comentario=comentario,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "admin/_aprovacao_panel.html",
        {"result": result},
    )
