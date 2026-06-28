from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from src.services import telegram_media_service as tms
from src.services.telegram_media_service import (
    AUDIO,
    DOCUMENTO,
    PHOTO,
    MediaRef,
    TelegramMediaError,
    extract_media,
    file_ext,
)


def _settings(*, token: str = "TESTTOKEN", reply: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        telegram_bot_token=token,
        telegram_api_base="https://api.telegram.org",
        telegram_reply_enabled=reply,
    )


def test_extract_media_photo_picks_largest() -> None:
    telegram = {
        "photo": [
            {"file_id": "small", "file_size": 100},
            {"file_id": "big", "file_size": 900},
        ]
    }
    refs = extract_media(telegram)
    assert len(refs) == 1
    assert refs[0].kind == PHOTO
    assert refs[0].file_id == "big"
    assert refs[0].mime_type == "image/jpeg"


def test_extract_media_voice_audio_document() -> None:
    telegram = {
        "voice": {"file_id": "v1", "mime_type": "audio/ogg"},
        "audio": {"file_id": "a1", "mime_type": "audio/mpeg", "file_name": "song.mp3"},
        "document": {"file_id": "d1", "file_name": "planilha.xlsx", "mime_type": "application/vnd"},
    }
    refs = extract_media(telegram)
    kinds = [r.kind for r in refs]
    assert kinds == [AUDIO, AUDIO, DOCUMENTO]
    assert refs[0].file_id == "v1"
    assert refs[2].file_name == "planilha.xlsx"


def test_extract_media_empty() -> None:
    assert extract_media({"text": "oi"}) == []


def test_file_ext_variants() -> None:
    assert file_ext(MediaRef(kind=PHOTO, file_id="x")) == "jpg"
    assert file_ext(MediaRef(kind=AUDIO, file_id="x", mime_type="audio/ogg")) == "ogg"
    assert file_ext(MediaRef(kind=DOCUMENTO, file_id="x", file_name="a.PDF")) == "pdf"
    assert file_ext(MediaRef(kind=DOCUMENTO, file_id="x")) == "bin"


async def test_download_file_two_step(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tms, "get_settings", lambda: _settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if "getFile" in request.url.path:
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/f.jpg"}})
        return httpx.Response(200, content=b"BINARY")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        data = await tms.download_file("FILEID", client=client)
    finally:
        await client.aclose()
    assert data == b"BINARY"


async def test_download_file_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tms, "get_settings", lambda: _settings(token=""))
    with pytest.raises(TelegramMediaError):
        await tms.download_file("FILEID")


async def test_send_message_disabled_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tms, "get_settings", lambda: _settings(reply=False))
    assert await tms.send_message(123, "oi") is False


async def test_send_message_enabled_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tms, "get_settings", lambda: _settings(reply=True))
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        ok = await tms.send_message(123, "oi", client=client)
    finally:
        await client.aclose()
    assert ok is True
    assert "sendMessage" in str(seen["path"])
