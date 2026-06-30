from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.errors import NotFoundError
from src.db.models import Obra
from src.services import rdo_aggregator_service


def _scalars_result(items: list[object]) -> MagicMock:
    scalars = MagicMock()
    scalars.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _rows_result(rows: list[tuple[object, object]]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


async def test_aggregate_daily_rdo_builds_structured_content() -> None:
    entrada_id = uuid.uuid4()
    arquivo_id = uuid.uuid4()
    foto_id = uuid.uuid4()
    audio_id = uuid.uuid4()
    triagem_id = uuid.uuid4()
    entrada = SimpleNamespace(
        id=entrada_id,
        source="openclaw",
        author="eng",
        text="executamos alvenaria",
        storage_uri="s3://bucket/envelope.json",
    )
    triagem = SimpleNamespace(
        id=triagem_id,
        entrada_id=entrada_id,
        documento_id=None,
        tipo_documento="rdo",
        confianca=0.9,
        resumo="Alvenaria executada",
        campos_extraidos={"pendencias": ["argamassa amanhã"]},
        acao_sugerida="incluir no RDO",
        precisa_aprovacao=True,
    )
    arquivo = SimpleNamespace(
        id=arquivo_id,
        entrada_id=entrada_id,
        tipo="documento",
        nome_original="nota.pdf",
        mime_type="application/pdf",
        bucket_uri="s3://bucket/nota.pdf",
        hash_sha256="h" * 64,
    )
    foto = SimpleNamespace(id=foto_id, data_foto=date(2026, 6, 27), descricao="Parede pronta")
    audio = SimpleNamespace(id=audio_id, transcricao="Equipe finalizou o trecho")
    session = AsyncMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Obra Um", slug="obra-um"))
    session.execute = AsyncMock(
        side_effect=[
            _scalars_result([entrada]),
            _scalars_result([triagem]),
            _scalars_result([arquivo]),
            _rows_result([(foto, arquivo)]),
            _rows_result([(audio, arquivo)]),
        ]
    )

    content = await rdo_aggregator_service.aggregate_daily_rdo(
        session, obra_id="OBRA-001", data_ref="2026-06-27"
    )

    assert content["tipo"] == "rdo"
    assert content["source_entrada_ids"] == [str(entrada_id)]
    assert str(arquivo_id) in content["source_arquivo_ids"]
    assert content["resumo_operacional"]["entradas_count"] == 1
    assert content["servicos"][0]["triagens"][0]["resumo"] == "Alvenaria executada"
    assert content["pendencias"] == ["argamassa amanhã"]
    assert content["fotos"][0]["descricao"] == "Parede pronta"
    assert content["audios"][0]["transcricao"] == "Equipe finalizou o trecho"
    assert content["documentos_brutos"][0]["nome_original"] == "nota.pdf"


async def test_aggregate_daily_rdo_requires_entries() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Obra Um", slug="obra-um"))
    session.execute = AsyncMock(return_value=_scalars_result([]))

    with pytest.raises(NotFoundError):
        await rdo_aggregator_service.aggregate_daily_rdo(
            session, obra_id="OBRA-001", data_ref="2026-06-27"
        )
