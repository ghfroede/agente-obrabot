import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.errors import ApprovalRequiredError, NotFoundError
from src.db.models import Documento
from src.schemas.domain import ApprovalRequest, RdoApproveRequest, RdoDraftRequest
from src.services import approval_service, rdo_service

router = APIRouter(prefix="/api/v1", tags=["rdo", "approvals", "documentos"])


@router.post("/rdo/rascunho")
async def rdo_rascunho(
    body: RdoDraftRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await rdo_service.create_rdo_draft(
            session,
            obra_id=body.obra_id,
            data_ref=body.data_ref,
            conteudo=body.conteudo,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rdo/finalizar")
async def rdo_finalizar(
    body: RdoApproveRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await rdo_service.finalize_rdo(
            session,
            documento_id=body.documento_id,
            aprovador=body.aprovador,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/aprovacoes")
async def aprovar(
    body: ApprovalRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await approval_service.approve_document(
            session,
            documento_id=body.documento_id,
            aprovado=body.aprovado,
            aprovador=body.aprovador,
            comentario=body.comentario,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/documentos/{documento_id}")
async def obter_documento(
    documento_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await session.execute(select(Documento).where(Documento.id == documento_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return {
        "id": str(doc.id),
        "obra_id": doc.obra_id,
        "tipo": doc.tipo,
        "titulo": doc.titulo,
        "status": doc.status.value,
        "revisao": doc.revisao,
        "data_ref": doc.data_ref.isoformat() if doc.data_ref else None,
        "bucket_uri": doc.bucket_uri,
        "hash_sha256": doc.hash_sha256,
        "metadata_json": doc.metadata_json,
    }
