from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import DocumentStatus
from src.db.models import Documento, IdempotencyKey, Obra, TelegramMessage, Triagem
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

def idempotency_key(event_id: str, content_hash: str, obra_id: str) -> str:
    return f"{event_id}:{content_hash}:{obra_id}"


async def claim_idempotency(
    session: AsyncSession,
    *,
    event_id: str,
    content_hash: str,
    obra_id: str,
    source: str = "openclaw",
) -> IdempotencyKey | None:
    """Reivindica a chave atomicamente via INSERT ... ON CONFLICT DO NOTHING.

    Retorna ``None`` quando esta requisição venceu a corrida (deve processar);
    retorna a linha existente quando houve conflito (já em processamento/concluída).
    """
    key = idempotency_key(event_id, content_hash, obra_id)
    stmt = (
        pg_insert(IdempotencyKey)
        .values(
            key=key,
            event_id=event_id,
            obra_id=obra_id,
            source=source,
            status="processing",
            request_hash=content_hash,
        )
        .on_conflict_do_nothing(index_elements=["key"])
        .returning(IdempotencyKey.key)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is not None:
        return None
    existing = await session.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    return existing.scalar_one()


async def complete_idempotency(
    session: AsyncSession,
    *,
    event_id: str,
    content_hash: str,
    obra_id: str,
    result: dict[str, Any],
) -> None:
    """Marca a chave como concluída e guarda a resposta."""
    key = idempotency_key(event_id, content_hash, obra_id)
    await session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.key == key)
        .values(status="completed", response_json=result, updated_at=datetime.now(UTC))
    )


async def fail_idempotency(
    session: AsyncSession,
    *,
    event_id: str,
    content_hash: str,
    obra_id: str,
    error: str,
) -> None:
    """Marca a chave como falha para permitir reprocessamento futuro."""
    key = idempotency_key(event_id, content_hash, obra_id)
    await session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.key == key)
        .values(status="failed", error=error[:500], updated_at=datetime.now(UTC))
    )

async def process_telegram_event(
    session: AsyncSession,
    payload: OpenClawTelegramPayload,
    headers: Mapping[str, str],
) -> dict[str, Any]:
    """Processa evento do Telegram com idempotência e auditoria."""
    obra = await ensure_obra(session, payload.obra_id, payload.obra_nome)
    tg = payload.telegram
    text = tg.text or tg.caption or ""

    # ===== 1. Calcula hash do conteúdo para idempotência =====
    content = f"{text}:{payload.obra_id}:{tg.chat.id}"
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # ===== 2. Reivindica idempotência atomicamente =====
    claim = await claim_idempotency(
        session,
        event_id=payload.event_id,
        content_hash=content_hash,
        obra_id=obra.id,
        source="openclaw",
    )
    if claim is not None:
        if claim.status == "completed" and claim.response_json is not None:
            return claim.response_json
        return {"status": "duplicate", "event_id": payload.event_id, "estado": claim.status}
    # Commit imediato torna o 'processing' visível para requisições concorrentes.
    await session.commit()

    try:
        # ===== 3. Persiste mensagem no banco =====
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

        # ===== 4. Persiste raw no S3 (FONTE DE VERDADE!) =====
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

        # ===== 5. Classificação (DEPOIS de persistir!) =====
        triagem = await openai_service.triagem_structured(
            text or "[mensagem sem texto — mídia]",
            context={
                "obra_id": obra.id,
                "has_photo": bool(tg.photo),
                "has_voice": bool(tg.voice),
            },
        )

        # ===== 6. Cria documento e triagem =====
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

        # ===== 7. Log de auditoria =====
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

        # ===== 8. Prepara resultado =====
        result = {
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

        # ===== 9. Conclui idempotência e persiste tudo =====
        await complete_idempotency(
            session,
            event_id=payload.event_id,
            content_hash=content_hash,
            obra_id=obra.id,
            result=result,
        )
        await session.commit()
        return result
    except Exception as exc:
        # Marca a chave como falha (permite reprocessar) sem perder o registro.
        await session.rollback()
        await fail_idempotency(
            session,
            event_id=payload.event_id,
            content_hash=content_hash,
            obra_id=obra.id,
            error=str(exc),
        )
        await session.commit()
        raise
