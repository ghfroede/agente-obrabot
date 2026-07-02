from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.routes.admin_common import (
    ENTRADA_STATUSES,
    check_same_origin,
    is_htmx,
    rdo_campos_form,
    require_admin_session,
    templates,
)
from src.core.constants import PENDING_OBRA_STATUS, DocumentStatus
from src.core.errors import ApprovalRequiredError, NotFoundError, ValidationError
from src.db.models import Obra
from src.schemas.obras import ObraCreate
from src.services import (
    admin_service,
    approval_service,
    entrada_service,
    obra_service,
    rdo_aggregator_service,
    rdo_service,
)
from src.utils.dates import today_iso

router = APIRouter(dependencies=[Depends(require_admin_session)])

DOCUMENTO_STATUSES: tuple[str, ...] = tuple(s.value for s in DocumentStatus)


@router.get("/")
async def dashboard(request: Request, session: AsyncSession = Depends(get_db)) -> Any:
    counts = await admin_service.dashboard_counts(session)
    return templates.TemplateResponse(request, "admin/dashboard.html", {"counts": counts})


@router.get("/obras")
async def obras_list(request: Request, session: AsyncSession = Depends(get_db)) -> Any:
    obras = await obra_service.list_obras(session)
    return templates.TemplateResponse(request, "admin/obras.html", {"obras": obras})


@router.get("/obras/nova")
async def obra_nova_form(request: Request) -> Any:
    return templates.TemplateResponse(
        request,
        "admin/obra_form.html",
        {"obra": None, "editar": False, "erro": None},
    )


@router.post("/obras/nova")
async def obra_nova_submit(
    request: Request,
    id: str = Form(...),
    nome: str = Form(...),
    status: str = Form("ativa"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    check_same_origin(request)
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


@router.get("/obras/{obra_id}/editar")
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


@router.post("/obras/{obra_id}/editar")
async def obra_editar_submit(
    obra_id: str,
    request: Request,
    nome: str = Form(...),
    status: str = Form("ativa"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    check_same_origin(request)
    existing = await session.get(Obra, obra_id)
    if existing is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    payload = ObraCreate(id=obra_id, nome=nome, status=status)
    await obra_service.upsert_obra(session, payload)
    await session.commit()
    return RedirectResponse("/admin/obras", status_code=303)


@router.post("/obras/{obra_id}/status")
async def obra_toggle_status(
    obra_id: str, request: Request, session: AsyncSession = Depends(get_db)
) -> Any:
    check_same_origin(request)
    obra = await session.get(Obra, obra_id)
    if obra is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    novo_status = "inativa" if obra.status == "ativa" else "ativa"
    obra = await obra_service.set_status(session, obra_id, novo_status)
    await session.commit()
    return templates.TemplateResponse(request, "admin/_obra_row.html", {"obra": obra})


@router.get("/dia-obra")
async def dia_obra(
    request: Request,
    obra_id: str | None = Query(default=None),
    data_ref: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> Any:
    obras = await obra_service.list_obras(session)
    selected_data_ref = data_ref or today_iso()
    selected_obra_id = obra_id or ""
    conteudo: dict[str, Any] | None = None
    erro: str | None = None

    if selected_obra_id:
        try:
            conteudo = await rdo_aggregator_service.aggregate_daily_rdo(
                session, obra_id=selected_obra_id, data_ref=selected_data_ref
            )
        except (NotFoundError, ValidationError, ValueError) as exc:
            erro = str(exc)

    return templates.TemplateResponse(
        request,
        "admin/dia_obra.html",
        {
            "obras": obras,
            "obra_id": selected_obra_id,
            "data_ref": selected_data_ref,
            "conteudo": conteudo,
            "erro": erro,
        },
    )


@router.post("/dia-obra/gerar-rdo")
async def dia_obra_gerar_rdo(
    request: Request,
    obra_id: str = Form(...),
    data_ref: str = Form(...),
    session: AsyncSession = Depends(get_db),
) -> Any:
    check_same_origin(request)
    obras = await obra_service.list_obras(session)
    try:
        conteudo = await rdo_aggregator_service.aggregate_daily_rdo(
            session, obra_id=obra_id, data_ref=data_ref
        )
        result = await rdo_service.create_rdo_draft(
            session, obra_id=obra_id, data_ref=data_ref, conteudo=conteudo
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        return templates.TemplateResponse(
            request,
            "admin/dia_obra.html",
            {
                "obras": obras,
                "obra_id": obra_id,
                "data_ref": data_ref,
                "conteudo": None,
                "erro": str(exc),
            },
            status_code=200,
        )

    return RedirectResponse(
        f"/admin/documentos/{result['documento_id']}", status_code=303
    )


@router.get("/entradas")
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
    template = "admin/_entradas_table.html" if is_htmx(request) else "admin/entradas.html"
    return templates.TemplateResponse(request, template, ctx)


@router.get("/entradas/{entrada_id}")
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
            "is_pending": entrada.status == PENDING_OBRA_STATUS,
        },
    )


@router.post("/entradas/{entrada_id}/resolver-obra")
async def entrada_resolver_obra(
    entrada_id: uuid.UUID,
    request: Request,
    obra_id: str = Form(...),
    session: AsyncSession = Depends(get_db),
) -> Any:
    check_same_origin(request)
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


@router.get("/documentos")
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
        "admin/_documentos_table.html" if is_htmx(request) else "admin/documentos.html"
    )
    return templates.TemplateResponse(request, template, ctx)


@router.get("/documentos/{documento_id}")
async def documento_detail(
    documento_id: uuid.UUID,
    request: Request,
    rdo_campos: str | None = Query(default=None),
    rdo_finalizado: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> Any:
    found = await admin_service.get_documento_com_triagem(session, documento_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    doc, triagem = found
    is_rdo = doc.tipo == "rdo"
    return templates.TemplateResponse(
        request,
        "admin/documento_detail.html",
        {
            "documento": doc,
            "triagem": triagem,
            "aguardando_aprovacao": doc.status in admin_service.AGUARDANDO_APROVACAO,
            "rdo_editable": is_rdo and doc.status in rdo_service.RDO_EDITABLE_STATUSES,
            "rdo_finalizable": is_rdo and doc.status == DocumentStatus.APROVADO,
            "rdo_campos": rdo_campos_form(doc) if is_rdo else {},
            "rdo_campos_sucesso": rdo_campos == "ok",
            "rdo_finalizado_sucesso": rdo_finalizado == "ok",
        },
    )


@router.post("/documentos/{documento_id}/rdo-campos")
async def documento_rdo_campos_submit(
    documento_id: uuid.UUID,
    request: Request,
    editor: str = Form("engenheiro"),
    clima: str | None = Form(default=None),
    equipe: str | None = Form(default=None),
    equipamentos: str | None = Form(default=None),
    observacoes: str | None = Form(default=None),
    complementos_engenheiro: str | None = Form(default=None),
    session: AsyncSession = Depends(get_db),
) -> Any:
    check_same_origin(request)
    try:
        await rdo_service.update_rdo_draft_fields(
            session,
            documento_id=str(documento_id),
            campos={
                "clima": clima,
                "equipe": equipe,
                "equipamentos": equipamentos,
                "observacoes": observacoes,
                "complementos_engenheiro": complementos_engenheiro,
            },
            editor=editor,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        f"/admin/documentos/{documento_id}?rdo_campos=ok", status_code=303
    )


@router.post("/documentos/{documento_id}/finalizar-rdo")
async def documento_finalizar_rdo(
    documento_id: uuid.UUID,
    request: Request,
    aprovador: str = Form("engenheiro"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    check_same_origin(request)
    try:
        await rdo_service.finalize_rdo(
            session, documento_id=str(documento_id), aprovador=aprovador
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        f"/admin/documentos/{documento_id}?rdo_finalizado=ok", status_code=303
    )


@router.post("/documentos/{documento_id}/aprovar")
async def documento_aprovar(
    documento_id: uuid.UUID,
    request: Request,
    aprovado: bool = Form(...),
    aprovador: str = Form("engenheiro"),
    comentario: str | None = Form(default=None),
    session: AsyncSession = Depends(get_db),
) -> Any:
    check_same_origin(request)
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
