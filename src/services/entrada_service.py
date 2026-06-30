from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, date, datetime
from typing import Any

from redis import Redis
from rq import Queue, Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.core.constants import DocumentStatus
from src.db.client import AsyncSessionLocal
from src.db.models import Documento, EntradaBruta, Obra, Task, TaskStatus, TelegramMessage
from src.schemas.domain import OpenClawTelegramPayload
from src.services import (
    audit_service,
    bucket_service,
    ingestao_service,
    media_service,
    obra_service,
    openai_service,
    telegram_context_service,
    telegram_media_service,
)

PENDING_OBRA_STATUS = "pending_obra"
PENDING_OBRA_IDEMPOTENCY_SCOPE = "__PENDING_OBRA__"


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
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue("obrabot", connection=redis_conn)
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
    """OpenClaw/Telegram: idempotência atômica + EntradaBruta + enfileira (responde rápido/202).

    Não roda IA aqui — o processamento pesado vai para a fila RQ (``process_entrada``).
    """
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
    data_ref = _date_from_telegram(raw.get("telegram", {}))
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
    data_ref = _date_from_telegram(raw.get("telegram", {}))
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
        "mensagem": _pending_obra_message(obras, requested_obra_id=requested_obra_id),
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


def _pending_obra_message(
    obras: list[dict[str, str]], *, requested_obra_id: str | None = None
) -> str:
    prefix = (
        f"A obra {requested_obra_id} não está cadastrada. "
        if requested_obra_id
        else "Recebi a mensagem, mas preciso confirmar a obra antes de processar. "
    )
    if not obras:
        return (
            f"{prefix}Nenhuma obra ativa está cadastrada. "
            "Cadastre uma obra antes de gerar documento oficial."
        )
    if len(obras) == 1:
        obra = obras[0]
        return (
            f"{prefix}"
            f"Use {obra['id']} ({obra['nome']}) ou responda com o ID da obra."
        )
    ids = ", ".join(f"{obra['id']} ({obra['nome']})" for obra in obras[:5])
    return (
        f"{prefix}"
        f"Obras ativas: {ids}. Responda com o ID da obra."
    )


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
            reply = _build_reply(entrada, result)
            await session.commit()
            if reply is not None:
                await _send_reply(*reply)
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
    if not entrada.obra_id:
        return {
            "entrada_id": str(entrada.id),
            "status": PENDING_OBRA_STATUS,
            "obra_id": None,
            "acao_sugerida": "confirmar_obra",
        }

    obra = await ingestao_service.ensure_obra(session, entrada.obra_id)

    # 1. Persiste raw no bucket (FONTE DE VERDADE) ANTES da IA.
    envelope = entrada.raw_payload or {"text": entrada.text}
    message_id = None
    telegram = envelope.get("telegram")
    if isinstance(telegram, dict):
        message_id = telegram.get("message_id")

    bucket_key, bucket_uri = bucket_service.persist_entrada_bruta(
        obra_id=obra.id,
        event_id=entrada.event_id or str(entrada.id),
        envelope={"entrada_id": str(entrada.id), "source": entrada.source, **envelope},
        source=entrada.source,
        slug=obra.slug,
        message_id=message_id,
        data_ref=entrada.data_ref,
        entrada_id=str(entrada.id),
    )
    entrada.storage_key = bucket_key
    entrada.storage_uri = bucket_uri

    # 2. Mídia (foto/áudio/documento): baixa do Telegram, persiste Arquivo e roda
    #    visão/transcrição. Falha de uma mídia degrada — o raw já é fonte de verdade.
    midias = await _process_media(session, entrada, obra.id, slug=obra.slug)

    # 3. Triagem (DEPOIS de persistir) — texto enriquecido com descrição/transcrição.
    text = _compose_triagem_text(entrada.text, midias)
    triagem = await openai_service.triagem_structured(
        text, context={"obra_id": obra.id, "source": entrada.source}
    )

    # 4. Documento + Triagem + Auditoria.
    doc = Documento(
        obra_id=obra.id,
        entrada_id=entrada.id,
        tipo=triagem.tipo_documento,
        titulo=f"{triagem.tipo_documento} — {str(entrada.id)[:8]}",
        revisao="REV00",
        status=DocumentStatus.TRIADO,
        arquivo_id=_primary_arquivo_id(midias),
        metadata_json={
            "entrada_bucket": bucket_uri,
            "entrada_bucket_key": bucket_key,
            "entrada_id": str(entrada.id),
            "texto": entrada.text,
            "source": entrada.source,
            "data_ref": entrada.data_ref.isoformat() if entrada.data_ref else None,
            "midias": midias,
        },
    )
    session.add(doc)
    await session.flush()
    triagem_row = await ingestao_service.save_triagem(
        session,
        obra_id=obra.id,
        output=triagem,
        entrada_id=entrada.id,
        telegram_message_id=await _find_telegram_message_id(session, entrada.event_id),
        documento_id=doc.id,
    )
    bucket_service.persist_triagem_json(
        obra_id=obra.id,
        triagem_id=str(triagem_row.id),
        payload=triagem.model_dump(),
        slug=obra.slug,
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
            "entrada_id": str(entrada.id),
            "event_id": entrada.event_id,
            "tipo_documento": triagem.tipo_documento,
            "bucket_key": bucket_key,
            "midias": [m.get("kind") for m in midias],
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
        "midias": midias,
        "status": doc.status.value,
    }


async def _process_media(
    session: AsyncSession, entrada: EntradaBruta, obra_id: str, *, slug: str | None = None
) -> list[dict[str, Any]]:
    """Baixa e persiste mídias do payload Telegram (foto/áudio/documento)."""
    raw = entrada.raw_payload or {}
    telegram = raw.get("telegram")
    if not isinstance(telegram, dict):
        return []
    refs = telegram_media_service.extract_media(telegram)
    if not refs:
        return []

    tg_msg_id = await _find_telegram_message_id(session, entrada.event_id)
    data_ref = _date_from_telegram(telegram)
    results: list[dict[str, Any]] = []
    for ref in refs:
        try:
            data = await telegram_media_service.download_file(ref.file_id)
            summary = await media_service.ingest_media(
                session,
                obra_id=obra_id,
                ref=ref,
                data=data,
                entrada_id=entrada.id,
                telegram_message_id=tg_msg_id,
                data_ref=data_ref,
                slug=slug,
            )
        except Exception as exc:
            # Degrada por mídia — não derruba a entrada (raw já persistido).
            summary = {"kind": ref.kind, "file_id": ref.file_id, "erro": str(exc)[:200]}
        results.append(summary)
    return results


async def _find_telegram_message_id(
    session: AsyncSession, event_id: str | None
) -> uuid.UUID | None:
    if not event_id:
        return None
    result = await session.execute(
        select(TelegramMessage.id).where(TelegramMessage.event_id == event_id)
    )
    return result.scalar_one_or_none()


def _date_from_telegram(telegram: dict[str, Any]) -> date | None:
    ts = telegram.get("date")
    if not isinstance(ts, int):
        return None
    return datetime.fromtimestamp(ts, UTC).date()


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


def _compose_triagem_text(text: str | None, midias: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if text:
        parts.append(text)
    for m in midias:
        if m.get("descricao"):
            parts.append(f"[Foto] {m['descricao']}")
        if m.get("transcricao"):
            parts.append(f"[Áudio] {m['transcricao']}")
    return "\n".join(parts) or "[mensagem sem texto — mídia]"


def _primary_arquivo_id(midias: list[dict[str, Any]]) -> uuid.UUID | None:
    for m in midias:
        aid = m.get("arquivo_id")
        if aid:
            return uuid.UUID(str(aid))
    return None


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


def _build_reply(entrada: EntradaBruta, result: dict[str, Any]) -> tuple[int, str] | None:
    """Monta (chat_id, texto) de status para o engenheiro a partir do payload Telegram.

    Lido antes do commit (atributos ainda carregados). Retorna ``None`` quando não há
    chat de origem; o envio em si é gated por ``telegram_reply_enabled``.
    """
    raw = entrada.raw_payload or {}
    telegram = raw.get("telegram")
    if not isinstance(telegram, dict):
        return None
    chat = telegram.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return None

    if result.get("status") == PENDING_OBRA_STATUS:
        return int(chat["id"]), str(result.get("mensagem") or "Confirme a obra para processar.")

    tipo = result.get("tipo_documento", "desconhecido")
    proximo = "aguardando aprovação" if result.get("precisa_aprovacao", True) else "registrado"
    documento_id = str(result.get("documento_id", ""))[:8]
    texto = f"✅ Recebido. Tipo: {tipo}. Status: {proximo}. Documento {documento_id}."
    return int(chat["id"]), texto


async def _send_reply(chat_id: int, texto: str) -> None:
    """Envia a resposta de status (best-effort) — falha de rede não derruba o pipeline."""
    try:
        await telegram_media_service.send_message(chat_id, texto)
    except Exception:
        return
