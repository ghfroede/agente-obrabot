from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.errors import NotFoundError, ValidationError
from src.db.models import CronogramaAtividade, Obra, OrcamentoItem
from src.services import orcamento_service


@pytest.mark.asyncio
async def test_import_orcamento_rejects_empty_list() -> None:
    session = AsyncMock()
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste")
    session.get = AsyncMock(return_value=obra)

    with pytest.raises(ValidationError, match="vazia"):
        await orcamento_service.import_orcamento(session, obra_id="OBRA-001", itens=[])


@pytest.mark.asyncio
async def test_import_orcamento_upserts_item() -> None:
    session = MagicMock()
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste")
    session.get = AsyncMock(return_value=obra)
    existing = MagicMock()
    existing.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=existing)
    session.commit = AsyncMock()

    with patch("src.services.orcamento_service.audit_service.log_event", new_callable=AsyncMock):
        result = await orcamento_service.import_orcamento(
            session,
            obra_id="OBRA-001",
            itens=[
                {
                    "codigo": "01.01",
                    "descricao": "Serviço teste",
                    "quantidade": 2,
                    "valor_unitario": 100,
                }
            ],
        )

    assert result["itens_processados"] == 1
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, OrcamentoItem)
    assert added.codigo == "01.01"


@pytest.mark.asyncio
async def test_import_cronograma_accepts_field_aliases() -> None:
    session = MagicMock()
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste")
    session.get = AsyncMock(return_value=obra)
    existing = MagicMock()
    existing.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=existing)
    session.commit = AsyncMock()

    with patch("src.services.orcamento_service.audit_service.log_event", new_callable=AsyncMock):
        result = await orcamento_service.import_cronograma(
            session,
            obra_id="OBRA-001",
            atividades=[
                {
                    "codigo": "ATV-1",
                    "descricao": "Fundação",
                    "inicio_planejado": "2026-06-01",
                    "fim_planejado": "2026-06-15",
                }
            ],
        )

    assert result["atividades_processadas"] == 1
    added = session.add.call_args[0][0]
    assert isinstance(added, CronogramaAtividade)
    assert added.nome == "Fundação"
    assert added.inicio_previsto == date(2026, 6, 1)


@pytest.mark.asyncio
async def test_validate_baseline_blocks_without_data() -> None:
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste", metadata_json={})
    session = AsyncMock()
    session.get = AsyncMock(return_value=obra)

    result = MagicMock()
    result.scalar_one.return_value = 0
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    report = await orcamento_service.validate_baseline(session, obra_id="OBRA-001")

    assert report["pronto_para_aprovacao"] is False
    assert len(report["bloqueios"]) == 2


@pytest.mark.asyncio
async def test_approve_baseline_persists_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste", metadata_json={})
    session = AsyncMock()
    session.get = AsyncMock(return_value=obra)
    session.commit = AsyncMock()

    monkeypatch.setattr(
        orcamento_service,
        "validate_baseline",
        AsyncMock(
            return_value={
                "pronto_para_aprovacao": True,
                "bloqueios": [],
                "avisos": [],
            }
        ),
    )
    monkeypatch.setattr(
        orcamento_service,
        "list_orcamento",
        AsyncMock(return_value={"itens": [{"codigo": "01.01"}]}),
    )
    monkeypatch.setattr(
        orcamento_service,
        "list_cronograma",
        AsyncMock(return_value={"atividades": [{"codigo": "ATV-1"}]}),
    )
    monkeypatch.setattr(
        orcamento_service.bucket_service,
        "put_bytes",
        lambda key, _body, **_kwargs: f"s3://test/{key}",
    )

    with patch("src.services.orcamento_service.audit_service.log_event", new_callable=AsyncMock):
        result = await orcamento_service.approve_baseline(
            session,
            obra_id="OBRA-001",
            aprovador="engenheiro",
        )

    assert result["status"] == "validado"
    assert obra.metadata_json is not None
    assert obra.metadata_json["baseline"]["status"] == "validado"


@pytest.mark.asyncio
async def test_import_orcamento_obra_not_found() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await orcamento_service.import_orcamento(
            session,
            obra_id="MISSING",
            itens=[{"codigo": "1", "descricao": "x"}],
        )
