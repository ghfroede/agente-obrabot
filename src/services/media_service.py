from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.db.models import Arquivo, AudioTranscricao, Foto
from src.services import bucket_service, openai_service
from src.services.telegram_media_service import (
    AUDIO,
    DOCUMENTO,
    PHOTO,
    MediaRef,
    file_ext,
    max_bytes_for_ref,
)
from src.utils.hashing import sha256_hex


class MediaSizeError(ValueError):
    """Mídia excede o limite configurado."""


def validate_media_size(ref: MediaRef, data: bytes) -> None:
    limit = max_bytes_for_ref(ref)
    if len(data) > limit:
        raise MediaSizeError(f"mídia excede limite de {limit} bytes")


async def persist_arquivo(
    session: AsyncSession,
    *,
    obra_id: str,
    ref: MediaRef,
    data: bytes,
    entrada_id: uuid.UUID | None = None,
    telegram_message_id: uuid.UUID | None = None,
    slug: str | None = None,
    data_ref: str | None = None,
) -> Arquivo:
    """Calcula hash, grava o binário no bucket (raw) e cria a linha ``Arquivo``."""
    validate_media_size(ref, data)
    file_hash = sha256_hex(data)
    ext = file_ext(ref)
    key = bucket_service.build_arquivo_key(
        obra_id,
        ref.kind,
        file_hash,
        ext,
        slug=slug,
        data_ref=data_ref,
    )
    uri = bucket_service.put_bytes(
        key, data, content_type=ref.mime_type or "application/octet-stream"
    )
    arquivo = Arquivo(
        obra_id=obra_id,
        entrada_id=entrada_id,
        telegram_message_id=telegram_message_id,
        tipo=ref.kind,
        nome_original=ref.file_name,
        mime_type=ref.mime_type,
        tamanho_bytes=len(data),
        hash_sha256=file_hash,
        bucket_key=key,
        bucket_uri=uri,
        metadata_json={
            "file_id": ref.file_id,
            "entrada_id": str(entrada_id) if entrada_id is not None else None,
        },
    )
    session.add(arquivo)
    await session.flush()
    return arquivo


async def ingest_media(
    session: AsyncSession,
    *,
    obra_id: str,
    ref: MediaRef,
    data: bytes,
    entrada_id: uuid.UUID | None = None,
    telegram_message_id: uuid.UUID | None = None,
    data_ref: date | None = None,
    slug: str | None = None,
) -> dict[str, Any]:
    """Persiste a mídia (Arquivo) e deriva o registro de domínio + IA por tipo.

    - ``foto`` → ``describe_image`` → ``Foto``
    - ``audio`` → ``transcribe_audio`` → ``AudioTranscricao``
    - ``documento`` → apenas ``Arquivo`` (OCR/importação em fase futura)

    Retorna um resumo (inclui ``descricao``/``transcricao`` quando houver) usado
    para compor o texto da triagem e a resposta de status.
    """
    settings = get_settings()
    arquivo = await persist_arquivo(
        session,
        obra_id=obra_id,
        ref=ref,
        data=data,
        entrada_id=entrada_id,
        telegram_message_id=telegram_message_id,
        slug=slug,
        data_ref=data_ref.isoformat() if data_ref else None,
    )
    summary: dict[str, Any] = {
        "kind": ref.kind,
        "arquivo_id": str(arquivo.id),
        "bucket_uri": arquivo.bucket_uri,
        "mime_type": ref.mime_type,
        "tamanho_bytes": arquivo.tamanho_bytes,
    }

    if ref.kind == PHOTO:
        descricao = await openai_service.describe_image(data)
        foto = Foto(
            obra_id=obra_id,
            arquivo_id=arquivo.id,
            data_foto=data_ref,
            descricao=descricao,
            metadata_json={
                "file_id": ref.file_id,
                "entrada_id": str(entrada_id) if entrada_id is not None else None,
            },
        )
        session.add(foto)
        await session.flush()
        summary["foto_id"] = str(foto.id)
        summary["descricao"] = descricao

    elif ref.kind == AUDIO:
        filename = ref.file_name or f"audio.{file_ext(ref)}"
        transcricao = await openai_service.transcribe_audio(data, filename)
        modelo = (
            settings.openai_transcription_model if settings.openai_api_key else "heuristic"
        )
        audio = AudioTranscricao(
            obra_id=obra_id,
            arquivo_id=arquivo.id,
            transcricao=transcricao,
            modelo=modelo,
            metadata_json={
                "file_id": ref.file_id,
                "entrada_id": str(entrada_id) if entrada_id is not None else None,
            },
        )
        session.add(audio)
        await session.flush()
        summary["audio_id"] = str(audio.id)
        summary["transcricao"] = transcricao

    elif ref.kind == DOCUMENTO:
        summary["nota"] = "documento salvo; OCR/importação em fase futura"

    return summary
