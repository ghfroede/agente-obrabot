from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models import Arquivo, AudioTranscricao, Foto
from src.services import media_service
from src.services.telegram_media_service import AUDIO, DOCUMENTO, PHOTO, MediaRef


def _patch_common(monkeypatch: pytest.MonkeyPatch, *, api_key: str = "") -> None:
    monkeypatch.setattr(
        media_service.bucket_service,
        "put_bytes",
        lambda key, data, **kw: f"s3://bucket/{key}",
    )
    monkeypatch.setattr(
        media_service,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key=api_key, openai_transcription_model="whisper-1"),
    )


async def test_ingest_media_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        media_service.openai_service,
        "describe_image",
        AsyncMock(return_value="uma parede de tijolos"),
    )
    session = AsyncMock()
    session.add = MagicMock()
    ref = MediaRef(kind=PHOTO, file_id="F1", mime_type="image/jpeg")

    summary = await media_service.ingest_media(session, obra_id="OBRA-001", ref=ref, data=b"img")

    assert summary["kind"] == PHOTO
    assert summary["descricao"] == "uma parede de tijolos"
    added = [c.args[0] for c in session.add.call_args_list]
    assert any(isinstance(o, Arquivo) for o in added)
    assert any(isinstance(o, Foto) for o in added)


async def test_ingest_media_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        media_service.openai_service,
        "transcribe_audio",
        AsyncMock(return_value="executamos alvenaria hoje"),
    )
    session = AsyncMock()
    session.add = MagicMock()
    ref = MediaRef(kind=AUDIO, file_id="A1", mime_type="audio/ogg")

    summary = await media_service.ingest_media(session, obra_id="OBRA-001", ref=ref, data=b"snd")

    assert summary["transcricao"] == "executamos alvenaria hoje"
    added = [c.args[0] for c in session.add.call_args_list]
    assert any(isinstance(o, AudioTranscricao) for o in added)


async def test_ingest_media_document_only_arquivo(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    session = AsyncMock()
    session.add = MagicMock()
    ref = MediaRef(kind=DOCUMENTO, file_id="D1", file_name="planilha.xlsx")

    summary = await media_service.ingest_media(session, obra_id="OBRA-001", ref=ref, data=b"doc")

    assert summary["kind"] == DOCUMENTO
    assert "nota" in summary
    added = [c.args[0] for c in session.add.call_args_list]
    assert [isinstance(o, Arquivo) for o in added] == [True]
