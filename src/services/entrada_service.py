from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from rq import Queue, Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import PENDING_OBRA_IDEMPOTENCY_SCOPE, PENDING_OBRA_STATUS
from src.core.redis import get_redis
from src.db.client import AsyncSessionLocal
from src.db.models import EntradaBruta, Obra, Task, TaskStatus, TelegramMessage
from src.schemas.domain import OpenClawTelegramPayload
from src.services import entrada_pipeline_steps as pipeline
from src.services import (
    ingestao_service,
    obra_service,
    telegram_context_service,
    telegram_media_service,
)
from src.services.telegram_reply import (
    build_telegram_reply,
    pending_obra_message,
    send_telegram_reply,
)

logger = logging.getLogger(__name__)


def content_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def create_entrada_bruta(
    session: AsyncSession,
    *,
    source: str,
    obra_id: str | None,
    text: str,
    raw_payload: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
    author: str | None = None,
    channel: str = "api",
    data_ref: date | None = None,
    event_id: str | None = None,
    idempotency_key: str | None = None,
    task_id: uuid.UUID | None = None,
    status: str = "received",
) -> EntradaBruta:
    """Cria a entrada bruta (status=received) — fonte única de ingestão de qualquer canal."""
    entrada = EntradaBruta(
        source=source,
        event_id=event_id,
        idempotency_key=idempotency_key,
        obra_id=obra_id,
        author=author,
        channel=channel,
        data_ref=data_ref,
        text=text,
        raw_payload=raw_payload,
        metadata_json=metadata_json,
        hash_sha256=content_hash(source, obra_id or "", text or ""),
        status=status,
        task_id=task_id,
    )
    session.add(entrada)
    await session.flush()
    return entrada


def enqueue_entrada(entrada_id: str) -> None:
    """Enfileira o processamento pesado na fila RQ 'obrabot'."""
    settings = get_settings()
    queue = Queue("obrabot", connection=get_redis())
    retry = (
        Retry(max=settings.rq_retry_max, interval=settings.rq_retry_intervals)
        if settings.rq_retry_max > 0
        else None
    )
    queue.enqueue(
        "src.worker.jobs.process_entrada",
        entrada_id,
        job_timeout=settings.rq_job_timeout_seconds,
        retry=retry,
    )


async def ingest_telegram(
    session: AsyncSession, payload: OpenClawTelegramPayload
) -> dict[str, Any]:
    """OpenClaw/Telegram: idempotência atômica + EntradaBruta + enfileira (responde rápido/202)."""
    tg = payload.telegram
    text = tg.text or tg.caption or ""
    resolution = await telegram_context_service.resolve_telegram_obra(session, payload, text)
    obra = resolution.obra
    if obra is None:
        return await _ingest_telegram_pending_obra(
            session,
            payload,
            text,
            requested_obra_id=resolution.requested_obra_id,
            resolution_source=resolution.source,
        )

    chash = content_hash(text, obra.id, str(tg.chat.id))

    claim = await ingestao_service.claim_idempotency(
        session, event_id=payload.event_id, content_hash=chash, obra_id=obra.id, source="openclaw"
    )
    if claim is not None:
        if claim.status == "completed" and claim.response_json is not None:
            return claim.response_json
        return {"status": "duplicate", "event_id": payload.event_id, "estado": claim.status}

    raw = payload.model_dump(mode="json")
    telegram_meta = _telegram_entrada_metadata(raw, obra_resolution_source=resolution.source)
    data_ref = pipeline.date_from_telegram(raw.get("telegram", {}))
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
        metadata_json=telegram_meta,
        author=(tg.from_user.username if tg.from_user else None),
        channel="telegram",
        data_ref=data_ref,
        event_id=payload.event_id,
        idempotency_key=ingestao_service.idempotency_key(payload.event_id, chash, obra.id),
    )

    result = {
        "status": "queued",
        "entrada_id": str(entrada.id),
        "event_id": payload.event_id,
        "obra_id": obra.id,
        "obra_resolution_source": resolution.source,
        "telegram_message_id": str(msg.id),
    }
    await ingestao_service.complete_idempotency(
        session, event_id=payload.event_id, content_hash=chash, obra_id=obra.id, result=result
    )
    await session.commit()

    await asyncio.to_thread(enqueue_entrada, str(entrada.id))
    return result


async def _ingest_telegram_pending_obra(
    session: AsyncSession,
    payload: OpenClawTelegramPayload,
    text: str,
    *,
    requested_obra_id: str | None = None,
    resolution_source: str = "missing",
) -> dict[str, Any]:
    tg = payload.telegram
    obra_scope = requested_obra_id or PENDING_OBRA_IDEMPOTENCY_SCOPE
    chash = content_hash(text, obra_scope, str(tg.chat.id))
    claim = await ingestao_service.claim_idempotency(
        session,
        event_id=payload.event_id,
        content_hash=chash,
        obra_id=obra_scope,
        source="openclaw",
    )
    if claim is not None:
        if claim.status == "completed" and claim.response_json is not None:
            return claim.response_json
        return {"status": "duplicate", "event_id": payload.event_id, "estado": claim.status}

    raw = payload.model_dump(mode="json")
    telegram_meta = _telegram_entrada_metadata(
        raw,
        requested_obra_id=requested_obra_id,
        obra_resolution_source=resolution_source,
    )
    data_ref = pipeline.date_from_telegram(raw.get("telegram", {}))
    msg = TelegramMessage(
        event_id=payload.event_id,
        obra_id=None,
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
        obra_id=None,
        text=text,
        raw_payload=raw,
        metadata_json=telegram_meta,
        author=(tg.from_user.username if tg.from_user else None),
        channel="telegram",
        data_ref=data_ref,
        event_id=payload.event_id,
        idempotency_key=ingestao_service.idempotency_key(
            payload.event_id, chash, PENDING_OBRA_IDEMPOTENCY_SCOPE
        ),
        status=PENDING_OBRA_STATUS,
    )
    obras = await obra_service.active_obras_summary(session)
    result = {
        "status": PENDING_OBRA_STATUS,
        "entrada_id": str(entrada.id),
        "event_id": payload.event_id,
        "obra_id": None,
        "obra_id_solicitado": requested_obra_id,
        "obra_resolution_source": resolution_source,
        "telegram_message_id": str(msg.id),
        "obras_disponiveis": obras,
        "mensagem": pending_obra_message(obras, requested_obra_id=requested_obra_id),
    }
    await ingestao_service.complete_idempotency(
        session,
        event_id=payload.event_id,
        content_hash=chash,
        obra_id=obra_scope,
        result=result,
    )
    await session.commit()
    return result


async def resolve_pending_obra(
    session: AsyncSession, *, entrada_id: uuid.UUID, obra_id: str
) -> dict[str, Any]:
    entrada = await session.get(EntradaBruta, entrada_id)
    if entrada is None:
        return {"status": "not_found"}
    if entrada.status != PENDING_OBRA_STATUS:
        return {
            "status": entrada.status,
            "entrada_id": str(entrada.id),
            "obra_id": entrada.obra_id,
            "queued": False,
        }

    resolved_obra_id = obra_id.strip().upper()
    obra = await session.get(Obra, resolved_obra_id)
    if obra is None:
        return {"status": "obra_not_found", "obra_id": resolved_obra_id}

    entrada.obra_id = obra.id
    entrada.status = "received"
    if isinstance(entrada.raw_payload, dict):
        entrada.raw_payload = {**entrada.raw_payload, "obra_id": obra.id}
    if isinstance(entrada.metadata_json, dict):
        entrada.metadata_json = {
            **entrada.metadata_json,
            "obra_resolvida_id": obra.id,
            "obra_resolvida_em": datetime.now(UTC).isoformat(),
        }

    if entrada.event_id:
        result = await session.execute(
            select(TelegramMessage).where(TelegramMessage.event_id == entrada.event_id)
        )
        msg = result.scalar_one_or_none()
        if msg is not None:
            msg.obra_id = obra.id
            if isinstance(msg.raw_payload, dict):
                msg.raw_payload = {**msg.raw_payload, "obra_id": obra.id}

    await session.commit()
    await asyncio.to_thread(enqueue_entrada, str(entrada.id))
    return {
        "status": "queued",
        "entrada_id": str(entrada.id),
        "obra_id": obra.id,
        "queued": True,
    }


async def run_entrada_pipeline(entrada_id: str) -> dict[str, Any]:
    """Worker: persiste raw (fonte de verdade), classifica e cria Documento/Triagem/Auditoria."""
    logger.info("entrada pipeline starting", extra={"entrada_id": entrada_id})
    async with AsyncSessionLocal() as session:
        entrada = await session.get(EntradaBruta, uuid.UUID(entrada_id))
        if entrada is None:
            logger.warning("entrada pipeline entrada not found", extra={"entrada_id": entrada_id})
            return {}
        entrada.status = "processing"
        await session.commit()
        try:
            result = await _process(session, entrada)
            entrada.status = "completed"
            entrada.processed_at = datetime.now(UTC)
            await _mark_task(session, entrada, TaskStatus.COMPLETED, result=result)
            reply = build_telegram_reply(entrada, result)
            await session.commit()
            if reply is not None:
                await send_telegram_reply(*reply)
            logger.info(
                "entrada pipeline completed",
                extra={
                    "entrada_id": entrada_id,
                    "obra_id": result.get("obra_id"),
                    "documento_id": result.get("documento_id"),
                },
            )
            return result
        except Exception as exc:
            logger.exception("entrada pipeline failed", extra={"entrada_id": entrada_id})
            await session.rollback()
            failed = await session.get(EntradaBruta, uuid.UUID(entrada_id))
            if failed is not None:
                failed.status = "failed"
                failed.processed_at = datetime.now(UTC)
                await _mark_task(session, failed, TaskStatus.FAILED, error=str(exc)[:500])
                await _fail_entrada_idempotency(session, failed, str(exc))
                await session.commit()
            raise


async def _fail_entrada_idempotency(
    session: AsyncSession, entrada: EntradaBruta, error: str
) -> None:
    if not entrada.idempotency_key:
        return
    parts = entrada.idempotency_key.split(":", 2)
    if len(parts) != 3:
        return
    event_id, content_hash_value, obra_id = parts
    await ingestao_service.fail_idempotency(
        session,
        event_id=event_id,
        content_hash=content_hash_value,
        obra_id=obra_id,
        error=error,
    )


async def _process(session: AsyncSession, entrada: EntradaBruta) -> dict[str, Any]:
    if not entrada.obra_id:
        return pipeline.pending_obra_result(entrada)

    obra = await ingestao_service.ensure_obra(session, entrada.obra_id)
    logger.info(
        "entrada processing",
        extra={"entrada_id": str(entrada.id), "obra_id": obra.id},
    )

    doc_existing, triagem_existing = await pipeline.load_existing_artifacts(session, entrada.id)
    if doc_existing is not None and triagem_existing is not None:
        return pipeline.result_from_existing(entrada, obra, doc_existing, triagem_existing)

    bucket_key, bucket_uri = await pipeline.persist_raw_bucket(session, entrada, obra)
    midias = await pipeline.process_media(session, entrada, obra.id, slug=obra.slug)
    triagem = await pipeline.run_triagem(entrada, obra, midias)
    doc, triagem_row = await pipeline.persist_documento_triagem(
        session,
        entrada=entrada,
        obra=obra,
        bucket_key=bucket_key,
        bucket_uri=bucket_uri,
        midias=midias,
        triagem=triagem,
        doc_existing=doc_existing,
        triagem_existing=triagem_existing,
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
        "midias": midias,
        "status": doc.status.value,
    }


def _telegram_entrada_metadata(
    raw: dict[str, Any],
    *,
    requested_obra_id: str | None = None,
    obra_resolution_source: str | None = None,
) -> dict[str, Any]:
    telegram = raw.get("telegram")
    if not isinstance(telegram, dict):
        return {}

    chat = telegram.get("chat")
    chat_meta = chat if isinstance(chat, dict) else {}
    user = telegram.get("from") or telegram.get("from_user")
    user_meta = user if isinstance(user, dict) else {}
    refs = telegram_media_service.extract_media(telegram)
    metadata: dict[str, Any] = {
        "canal": "telegram",
        "chat_id": chat_meta.get("id"),
        "chat_type": chat_meta.get("type"),
        "message_id": telegram.get("message_id"),
        "message_thread_id": telegram.get("message_thread_id"),
        "telegram_date": telegram.get("date"),
        "media_count": len(refs),
        "media": [
            {
                "kind": ref.kind,
                "file_id": ref.file_id,
                "mime_type": ref.mime_type,
                "file_name": ref.file_name,
                "file_size": ref.file_size,
            }
            for ref in refs
        ],
    }
    if user_meta:
        metadata["from_user"] = {
            "id": user_meta.get("id"),
            "username": user_meta.get("username"),
            "first_name": user_meta.get("first_name"),
        }
    if requested_obra_id:
        metadata["obra_id_solicitado"] = requested_obra_id
    if obra_resolution_source:
        metadata["obra_resolution_source"] = obra_resolution_source
    return metadata


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
