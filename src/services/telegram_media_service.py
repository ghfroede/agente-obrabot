from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import Any

import httpx

from src.config.env import get_settings

# Tipos de Arquivo.tipo / kind de mídia.
PHOTO = "foto"
AUDIO = "audio"
DOCUMENTO = "documento"


class TelegramMediaError(RuntimeError):
    """Falha ao baixar/enviar mídia via API do Telegram."""


@dataclass(frozen=True)
class MediaRef:
    """Referência a uma mídia do Telegram (file_id + metadados conhecidos)."""

    kind: str
    file_id: str
    mime_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None


def extract_media(telegram: dict[str, Any]) -> list[MediaRef]:
    """Extrai referências de mídia do envelope ``telegram`` (foto, voz, áudio, documento).

    Função pura — não baixa nada. Fotos vêm como lista de ``PhotoSize`` em ordem
    crescente; usamos a maior (última).
    """
    refs: list[MediaRef] = []

    photo = telegram.get("photo")
    if isinstance(photo, list) and photo:
        largest = photo[-1]
        refs.append(
            MediaRef(
                kind=PHOTO,
                file_id=str(largest["file_id"]),
                mime_type="image/jpeg",
                file_size=largest.get("file_size"),
            )
        )

    voice = telegram.get("voice")
    if isinstance(voice, dict) and voice.get("file_id"):
        refs.append(
            MediaRef(
                kind=AUDIO,
                file_id=str(voice["file_id"]),
                mime_type=voice.get("mime_type") or "audio/ogg",
                file_size=voice.get("file_size"),
            )
        )

    audio = telegram.get("audio")
    if isinstance(audio, dict) and audio.get("file_id"):
        refs.append(
            MediaRef(
                kind=AUDIO,
                file_id=str(audio["file_id"]),
                mime_type=audio.get("mime_type"),
                file_name=audio.get("file_name"),
                file_size=audio.get("file_size"),
            )
        )

    document = telegram.get("document")
    if isinstance(document, dict) and document.get("file_id"):
        refs.append(
            MediaRef(
                kind=DOCUMENTO,
                file_id=str(document["file_id"]),
                mime_type=document.get("mime_type"),
                file_name=document.get("file_name"),
                file_size=document.get("file_size"),
            )
        )

    return refs


def file_ext(ref: MediaRef) -> str:
    """Determina a extensão do arquivo (sem ponto) a partir do nome/mime/kind."""
    if ref.file_name and "." in ref.file_name:
        return ref.file_name.rsplit(".", 1)[1].lower()
    if ref.kind == PHOTO:
        return "jpg"
    if ref.kind == AUDIO and (ref.mime_type or "").endswith("ogg"):
        return "ogg"
    if ref.mime_type:
        guessed = mimetypes.guess_extension(ref.mime_type)
        if guessed:
            return guessed.lstrip(".")
    return "bin"


async def download_file(file_id: str, *, client: httpx.AsyncClient | None = None) -> bytes:
    """Baixa o conteúdo de uma mídia: ``getFile`` → resolve ``file_path`` → download binário.

    ``client`` é injetável para testes (ex.: ``httpx.MockTransport``).
    """
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        raise TelegramMediaError("TELEGRAM_BOT_TOKEN não configurado; mídia não pode ser baixada.")

    base = settings.telegram_api_base.rstrip("/")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        meta = await client.get(f"{base}/bot{token}/getFile", params={"file_id": file_id})
        meta.raise_for_status()
        body = meta.json()
        if not body.get("ok"):
            raise TelegramMediaError(f"getFile falhou: {body}")
        file_path = body["result"]["file_path"]

        download = await client.get(f"{base}/file/bot{token}/{file_path}")
        download.raise_for_status()
        return download.content
    finally:
        if owns_client:
            await client.aclose()


async def send_message(
    chat_id: int, text: str, *, client: httpx.AsyncClient | None = None
) -> bool:
    """Envia uma mensagem de texto ao chat (resposta de status ao engenheiro).

    Best-effort e gated por ``telegram_reply_enabled``: retorna ``False`` sem lançar
    quando desabilitado/sem token. ``client`` é injetável para testes.
    """
    settings = get_settings()
    if not settings.telegram_reply_enabled or not settings.telegram_bot_token:
        return False

    base = settings.telegram_api_base.rstrip("/")
    token = settings.telegram_bot_token
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        resp = await client.post(
            f"{base}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        resp.raise_for_status()
        return True
    finally:
        if owns_client:
            await client.aclose()
