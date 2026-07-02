from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import PENDING_OBRA_STATUS, DocumentStatus
from src.db.models import Documento, EntradaBruta, Obra, TelegramMessage, Triagem
from src.services import (
    audit_service,
    bucket_service,
    ingestao_service,
    media_service,
    openai_service,
    telegram_media_service,
)

logger = logging.getLogger(__name__)


async def load_existing_artifacts(
    session: AsyncSession, entrada_id: uuid.UUID
) -> tuple[Documento | None, Triagem | None]:
    doc_result = await session.execute(
        select(Documento).where(Documento.entrada_id == entrada_id).limit(1)
    )
    doc = doc_result.scalar_one_or_none()
    triagem_result = await session.execute(
        select(Triagem).where(Triagem.entrada_id == entrada_id).limit(1)
    )
    triagem = triagem_result.scalar_one_or_none()
    return doc, triagem


def result_from_existing(
    entrada: EntradaBruta, obra: Obra, doc: Documento, triagem_row: Triagem
) -> dict[str, Any]:
    metadata = doc.metadata_json if isinstance(doc.metadata_json, dict) else {}
    return {
        "entrada_id": str(entrada.id),
        "obra_id": obra.id,
        "documento_id": str(doc.id),
        "triagem_id": str(triagem_row.id),
        "tipo_documento": triagem_row.tipo_documento,
        "confianca": triagem_row.confianca,
        "resumo": triagem_row.resumo,
        "acao_sugerida": triagem_row.acao_sugerida,
        "precisa_aprovacao": triagem_row.precisa_aprovacao,
        "entrada_bucket_uri": entrada.storage_uri or metadata.get("entrada_bucket"),
        "midias": metadata.get("midias", []),
        "status": doc.status.value,
        "retomado": True,
    }


async def persist_raw_bucket(
    session: AsyncSession, entrada: EntradaBruta, obra: Obra
) -> tuple[str, str]:
    if entrada.storage_key and entrada.storage_uri:
        return entrada.storage_key, entrada.storage_uri

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
    return bucket_key, bucket_uri


async def process_media(
    session: AsyncSession, entrada: EntradaBruta, obra_id: str, *, slug: str | None = None
) -> list[dict[str, Any]]:
    raw = entrada.raw_payload or {}
    telegram = raw.get("telegram")
    if not isinstance(telegram, dict):
        return []
    refs = telegram_media_service.extract_media(telegram)
    if not refs:
        return []

    tg_msg_id = await find_telegram_message_id(session, entrada.event_id)
    data_ref = date_from_telegram(telegram)
    results: list[dict[str, Any]] = []
    for ref in refs:
        try:
            max_bytes = telegram_media_service.max_bytes_for_ref(ref)
            if ref.file_size is not None and ref.file_size > max_bytes:
                raise telegram_media_service.MediaTooLargeError(
                    f"mídia excede limite de {max_bytes} bytes"
                )
            data = await telegram_media_service.download_file(ref.file_id, max_bytes=max_bytes)
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
        except Exception:
            logger.warning(
                "media ingest failed",
                extra={"kind": ref.kind, "file_id": ref.file_id},
                exc_info=True,
            )
            summary = {
                "kind": ref.kind,
                "file_id": ref.file_id,
                "erro": "falha ao processar mídia",
            }
        results.append(summary)
    return results


async def run_triagem(
    entrada: EntradaBruta, obra: Obra, midias: list[dict[str, Any]]
) -> Any:
    text = compose_triagem_text(entrada.text, midias)
    return await openai_service.triagem_structured(
        text, context={"obra_id": obra.id, "source": entrada.source}
    )


async def persist_documento_triagem(
    session: AsyncSession,
    *,
    entrada: EntradaBruta,
    obra: Obra,
    bucket_key: str,
    bucket_uri: str,
    midias: list[dict[str, Any]],
    triagem: Any,
    doc_existing: Documento | None,
    triagem_existing: Triagem | None,
) -> tuple[Documento, Triagem]:
    if doc_existing is not None:
        doc = doc_existing
        if isinstance(doc.metadata_json, dict):
            doc.metadata_json = {**doc.metadata_json, "midias": midias}
    else:
        doc = Documento(
            obra_id=obra.id,
            entrada_id=entrada.id,
            tipo=triagem.tipo_documento,
            titulo=f"{triagem.tipo_documento} — {str(entrada.id)[:8]}",
            revisao="REV00",
            status=DocumentStatus.TRIADO,
            arquivo_id=primary_arquivo_id(midias),
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

    if triagem_existing is not None:
        return doc, triagem_existing

    triagem_row = await ingestao_service.save_triagem(
        session,
        obra_id=obra.id,
        output=triagem,
        entrada_id=entrada.id,
        telegram_message_id=await find_telegram_message_id(session, entrada.event_id),
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
    return doc, triagem_row


async def find_telegram_message_id(
    session: AsyncSession, event_id: str | None
) -> uuid.UUID | None:
    if not event_id:
        return None
    result = await session.execute(
        select(TelegramMessage.id).where(TelegramMessage.event_id == event_id)
    )
    return result.scalar_one_or_none()


def date_from_telegram(telegram: dict[str, Any]) -> date | None:
    ts = telegram.get("date")
    if not isinstance(ts, int):
        return None
    return datetime.fromtimestamp(ts, UTC).date()


def compose_triagem_text(text: str | None, midias: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if text:
        parts.append(text)
    for m in midias:
        if m.get("descricao"):
            parts.append(f"[Foto] {m['descricao']}")
        if m.get("transcricao"):
            parts.append(f"[Áudio] {m['transcricao']}")
    return "\n".join(parts) or "[mensagem sem texto — mídia]"


def primary_arquivo_id(midias: list[dict[str, Any]]) -> uuid.UUID | None:
    for m in midias:
        aid = m.get("arquivo_id")
        if aid:
            return uuid.UUID(str(aid))
    return None


def pending_obra_result(entrada: EntradaBruta) -> dict[str, Any]:
    return {
        "entrada_id": str(entrada.id),
        "status": PENDING_OBRA_STATUS,
        "obra_id": None,
        "acao_sugerida": "confirmar_obra",
    }
