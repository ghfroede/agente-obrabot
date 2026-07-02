from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from src.services import media_service
from src.services import telegram_media_service as tms
from src.services.telegram_media_service import PHOTO, MediaRef, MediaTooLargeError


def _settings(*, token: str = "TESTTOKEN") -> SimpleNamespace:
    return SimpleNamespace(
        telegram_bot_token=token,
        telegram_api_base="https://api.telegram.org",
        max_image_bytes=100,
        max_audio_bytes=200,
        max_document_bytes=300,
    )


def test_max_bytes_for_ref_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tms,
        "get_settings",
        lambda: SimpleNamespace(
            max_image_bytes=10,
            max_audio_bytes=20,
            max_document_bytes=30,
        ),
    )
    assert tms.max_bytes_for_ref(MediaRef(kind=PHOTO, file_id="x")) == 10


async def test_download_file_rejects_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tms, "get_settings", lambda: _settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if "getFile" in request.url.path:
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/f.jpg"}})
        return httpx.Response(200, content=b"x" * 50, headers={"content-length": "50"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MediaTooLargeError):
            await tms.download_file("FILEID", client=client, max_bytes=10)
    finally:
        await client.aclose()


async def test_download_file_rejects_oversized_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tms, "get_settings", lambda: _settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if "getFile" in request.url.path:
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/f.jpg"}})
        return httpx.Response(200, content=b"x" * 50)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MediaTooLargeError):
            await tms.download_file("FILEID", client=client, max_bytes=10)
    finally:
        await client.aclose()


async def test_persist_arquivo_rejects_oversized_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tms,
        "get_settings",
        lambda: SimpleNamespace(
            max_image_bytes=5,
            max_audio_bytes=5,
            max_document_bytes=5,
        ),
    )
    session = AsyncMock()
    ref = MediaRef(kind=PHOTO, file_id="F1", mime_type="image/jpeg")
    with pytest.raises(media_service.MediaSizeError):
        await media_service.persist_arquivo(
            session,
            obra_id="OBRA-001",
            ref=ref,
            data=b"123456",
            entrada_id=uuid4(),
        )


async def test_persist_arquivo_accepts_within_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tms,
        "get_settings",
        lambda: SimpleNamespace(
            max_image_bytes=100,
            max_audio_bytes=100,
            max_document_bytes=100,
        ),
    )
    monkeypatch.setattr(
        media_service.bucket_service,
        "put_bytes",
        lambda key, data, **kw: f"s3://bucket/{key}",
    )
    session = AsyncMock()
    session.add = MagicMock()
    ref = MediaRef(kind=PHOTO, file_id="F1", mime_type="image/jpeg")
    arquivo = await media_service.persist_arquivo(
        session,
        obra_id="OBRA-001",
        ref=ref,
        data=b"12345",
        entrada_id=uuid4(),
    )
    assert arquivo.tamanho_bytes == 5
