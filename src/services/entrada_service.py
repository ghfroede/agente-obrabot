from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import DocumentStatus
from src.db.client import AsyncSessionLocal
from src.db.models import Documento, EntradaBruta, Task, TaskStatus, TelegramMessage
from src.schemas.domain import OpenClawTelegramPayload
from src.services import audit_service, bucket_service, ingestao_service, openai_service


def content_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def create_entrada_bruta(
    session: AsyncSession,
    *,
    source: str,
    obra_id: str,
    text: str,
    raw_payload: dict[str, Any] | None = None,
    author: str | None = None,
    channel: str = "api",
    event_id: str | None = None,
    idempotency_key: str | None = None,
    task_id: uuid.UUID | None = None,
) -> EntradaBruta:
    """Cria a entrada bruta (status=received) — fonte única de ingestão de qualquer canal."""
    entrada = EntradaBruta(
        source=source,
        event_id=event_id,
        idempotency_key=idempotency_key,
        obra_id=obra_id,
        author=author,
        channel=channel,
        text=text,
        raw_payload=raw_payload,
        hash_sha256=content_hash(source, obra_id, text or ""),
        status="received",
        task_id=task_id,
    )
    session.add(entrada)
    await session.flush()
    return entrada


def enqueue_entrada(entrada_id: str) -> None:
    """Enfileira o processamento pesado na fila RQ 'obrabot'."""
    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue("obrabot", connection=redis_conn)
    queue.enqueue("src.worker.jobs.process_entrada", entrada_id, job_timeout=600)


async def ingest_telegram(
    session: AsyncSession, payload: OpenClawTelegramPayload
) -> dict[str, Any]:
    """OpenClaw/Telegram: idempotência atômica + EntradaBruta + enfileira (responde rápido/202).

    Não roda IA aqui — o processamento pesado vai para a fila RQ (``process_entrada``).
    """
    obra = await ingestao_service.ensure_obra(session, payload.obra_id, payload.obra_nome)
    tg = payload.telegram
    text = tg.text or tg.caption or ""
    chash = content_hash(text, obra.id, str(tg.chat.id))

    claim = await ingestao_service.claim_idempotency(
        session, event_id=payload.event_id, content_hash=chash, obra_id=obra.id, source="openclaw"
    )
    if claim is not None:
        if claim.status == "completed" and claim.response_json is not None:
            return claim.response_json
        return {"status": "duplicate", "event_id": payload.event_id, "estado": claim.status}

    raw = payload.model_dump(mode="json")
    msg = TelegramMessage(
        event_id=payload.event_id,
        obra_id=obra.id,
        chat_id=tg.chat.id,
        message_id=tg.message_id,
        user_id=tg.from_user.id if tg.from_user else None,
        text=text,
        raw_payload=raw,
    )
    session.add(msg)
    await session.flush()

    entrada = await create_entrada_bruta(
        session,
        source="openclaw",
        obra_id=obra.id,
        text=text,
        raw_payload=raw,
        author=(tg.from_user.username if tg.from_user else None),
        channel="telegram",
        event_id=payload.event_id,
        idempotency_key=ingestao_service.idempotency_key(payload.event_id, chash, obra.id),
    )

    result = {
        "status": "queued",
        "entrada_id": str(entrada.id),
        "event_id": payload.event_id,
        "obra_id": obra.id,
        "telegram_message_id": str(msg.id),
    }
    await ingestao_service.complete_idempotency(
        session, event_id=payload.event_id, content_hash=chash, obra_id=obra.id, result=result
    )
    await session.commit()

    await asyncio.to_thread(enqueue_entrada, str(entrada.id))
    return result


async def run_entrada_pipeline(entrada_id: str) -> dict[str, Any]:
    """Worker: persiste raw (fonte de verdade), classifica e cria Documento/Triagem/Auditoria.

    Abre a própria sessão async e atualiza ``EntradaBruta`` (e a ``Task`` ligada, se houver).
    """
    async with AsyncSessionLocal() as session:
        entrada = await session.get(EntradaBruta, uuid.UUID(entrada_id))
        if entrada is None:
            return {}
        entrada.status = "processing"
        await session.commit()
        try:
            result = await _process(session, entrada)
            entrada.status = "completed"
            entrada.processed_at = datetime.now(UTC)
            await _mark_task(session, entrada, TaskStatus.COMPLETED, result=result)
            await session.commit()
            return result
        except Exception as exc:
            await session.rollback()
            failed = await session.get(EntradaBruta, uuid.UUID(entrada_id))
            if failed is not None:
                failed.status = "failed"
                failed.processed_at = datetime.now(UTC)
                await _mark_task(session, failed, TaskStatus.FAILED, error=str(exc)[:500])
                await session.commit()
            raise


async def _process(session: AsyncSession, entrada: EntradaBruta) -> dict[str, Any]:
    obra = await ingestao_service.ensure_obra(session, entrada.obra_id)
    text = entrada.text or "[mensagem sem texto — mídia]"

    # 1. Persiste raw no bucket (FONTE DE VERDADE) ANTES da IA.
    envelope = entrada.raw_payload or {"text": entrada.text}
    bucket_key, bucket_uri = bucket_service.persist_entrada_bruta(
        obra_id=obra.id,
        event_id=entrada.event_id or str(entrada.id),
        envelope={"entrada_id": str(entrada.id), "source": entrada.source, **envelope},
        source=entrada.source,
    )
    entrada.storage_key = bucket_key
    entrada.storage_uri = bucket_uri

    # 2. Triagem (DEPOIS de persistir).
    triagem = await openai_service.triagem_structured(
        text, context={"obra_id": obra.id, "source": entrada.source}
    )

    # 3. Documento + Triagem + Auditoria.
    doc = Documento(
        obra_id=obra.id,
        tipo=triagem.tipo_documento,
        titulo=f"{triagem.tipo_documento} — {str(entrada.id)[:8]}",
        revisao="REV00",
        status=DocumentStatus.TRIADO,
        metadata_json={
            "entrada_bucket": bucket_uri,
            "texto": entrada.text,
            "source": entrada.source,
        },
    )
    session.add(doc)
    await session.flush()
    triagem_row = await ingestao_service.save_triagem(
        session, obra_id=obra.id, output=triagem, documento_id=doc.id
    )
    await audit_service.log_event(
        session,
        entidade="entrada_bruta",
        entidade_id=str(entrada.id),
        acao="ingestao",
        obra_id=obra.id,
        actor=entrada.author,
        detalhes={
            "source": entrada.source,
            "event_id": entrada.event_id,
            "tipo_documento": triagem.tipo_documento,
            "bucket_key": bucket_key,
        },
    )
    return {
        "entrada_id": str(entrada.id),
        "obra_id": obra.id,
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


async def _mark_task(
    session: AsyncSession,
    entrada: EntradaBruta,
    status: TaskStatus,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    if entrada.task_id is None:
        return
    task = await session.get(Task, entrada.task_id)
    if task is None:
        return
    task.status = status
    task.finished_at = datetime.now(UTC)
    if result is not None:
        task.result = result
        task.error = None
    if error is not None:
        task.error = error
