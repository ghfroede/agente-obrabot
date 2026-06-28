from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import DocumentStatus
from src.db.models import Documento, Obra, TelegramMessage, Triagem
from src.schemas.domain import OpenClawTelegramPayload, TriagemOutput
from src.services import audit_service, bucket_service, openai_service
from src.utils.filenames import obra_slug


async def ensure_obra(
    session: AsyncSession,
    obra_id: str,
    nome: str | None = None,
) -> Obra:
    result = await session.execute(select(Obra).where(Obra.id == obra_id))
    obra = result.scalar_one_or_none()
    if obra is None:
        obra = Obra(
            id=obra_id,
            nome=nome or obra_id,
            slug=obra_slug(nome or obra_id),
            status="ativa",
        )
        session.add(obra)
        await session.flush()
    elif nome and obra.nome != nome:
        obra.nome = nome
        obra.slug = obra_slug(nome)
    return obra


async def save_triagem(
    session: AsyncSession,
    *,
    obra_id: str,
    output: TriagemOutput,
    telegram_message_id: uuid.UUID | None = None,
    documento_id: uuid.UUID | None = None,
) -> Triagem:
    row = Triagem(
        obra_id=obra_id,
        telegram_message_id=telegram_message_id,
        documento_id=documento_id,
        tipo_documento=output.tipo_documento,
        confianca=output.confianca,
        resumo=output.resumo,
        campos_extraidos=output.campos_extraidos,
        acao_sugerida=output.acao_sugerida,
        precisa_aprovacao=output.precisa_aprovacao,
        modelo=get_settings().openai_model if get_settings().openai_api_key else "heuristic",
    )
    session.add(row)
    await session.flush()
    return row


async def process_telegram_event(
    session: AsyncSession,
    payload: OpenClawTelegramPayload,
) -> dict[str, Any]:
    obra = await ensure_obra(session, payload.obra_id, payload.obra_nome)
    tg = payload.telegram
    text = tg.text or tg.caption or ""

    existing = await session.execute(
        select(TelegramMessage).where(TelegramMessage.event_id == payload.event_id)
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "event_id": payload.event_id}

    msg = TelegramMessage(
        event_id=payload.event_id,
        obra_id=obra.id,
        chat_id=tg.chat.id,
        message_id=tg.message_id,
        user_id=tg.from_user.id if tg.from_user else None,
        text=text,
        raw_payload=payload.model_dump(mode="json"),
    )
    session.add(msg)
    await session.flush()

    envelope = {
        "event_id": payload.event_id,
        "obra_id": obra.id,
        "obra_nome": obra.nome,
        "telegram": payload.model_dump(mode="json"),
    }
    bucket_key, bucket_uri = bucket_service.persist_entrada_bruta(
        obra_id=obra.id,
        event_id=payload.event_id,
        envelope=envelope,
    )

    triagem = await openai_service.triagem_structured(
        text or "[mensagem sem texto — mídia]",
        context={"obra_id": obra.id, "has_photo": bool(tg.photo), "has_voice": bool(tg.voice)},
    )
    doc = Documento(
        obra_id=obra.id,
        tipo=triagem.tipo_documento,
        titulo=f"{triagem.tipo_documento} — {payload.event_id[:8]}",
        data_ref=None,
        revisao="REV00",
        status=DocumentStatus.TRIADO,
        metadata_json={"entrada_bucket": bucket_uri, "texto": text},
    )
    session.add(doc)
    await session.flush()

    triagem_row = await save_triagem(
        session,
        obra_id=obra.id,
        output=triagem,
        telegram_message_id=msg.id,
        documento_id=doc.id,
    )

    await audit_service.log_event(
        session,
        entidade="telegram_message",
        entidade_id=str(msg.id),
        acao="ingestao",
        obra_id=obra.id,
        detalhes={
            "event_id": payload.event_id,
            "tipo_documento": triagem.tipo_documento,
            "bucket_key": bucket_key,
        },
    )
    await session.commit()

    return {
        "event_id": payload.event_id,
        "obra_id": obra.id,
        "telegram_message_id": str(msg.id),
        "documento_id": str(doc.id),
        "triagem_id": str(triagem_row.id),
        "tipo_documento": triagem.tipo_documento,
        "confianca": triagem.confianca,
        "resumo": triagem.resumo,
        "acao_sugerida": triagem.acao_sugerida,
        "precisa_aprovacao": triagem.precisa_aprovacao,
        "entrada_bucket_uri": bucket_uri,
        "status": doc.status.value,
    }
