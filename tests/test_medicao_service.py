from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.core.errors import NotFoundError, ValidationError
from src.db.models import Medicao, MedicaoPeriodo, MedicaoPeriodoStatus, Obra, OrcamentoItem
from src.schemas.domain import MedicaoRegistroRequest
from src.services import medicao_service


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _rows_result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def test_medicao_schema_accepts_openclaw_aliases() -> None:
    payload = MedicaoRegistroRequest.model_validate(
        {
            "obraId": "OBRA-001",
            "periodo": "2026-06",
            "items": [
                {
                    "codigo_orcamento": "03.02.001",
                    "quantidade": 5,
                    "valor": 1200,
                    "obs": "medição parcial",
                }
            ],
        }
    )

    assert payload.obra_id == "OBRA-001"
    assert payload.periodo_ref == "2026-06"
    assert payload.itens[0].codigo_orcamento == "03.02.001"
    assert payload.itens[0].quantidade_medida == 5
    assert payload.itens[0].valor_medido == 1200
    assert payload.itens[0].observacoes == "medição parcial"


def test_medicao_schema_rejects_negative_quantity() -> None:
    with pytest.raises(PydanticValidationError):
        MedicaoRegistroRequest.model_validate(
            {
                "obra_id": "OBRA-001",
                "periodo_ref": "2026-06",
                "itens": [{"codigo": "03.02.001", "quantidade": -1}],
            }
        )


@pytest.mark.asyncio
async def test_registrar_medicao_creates_period_and_items() -> None:
    obra = Obra(id="OBRA-001", nome="Teste", slug="obra-teste")
    orc_item = OrcamentoItem(
        id=uuid.uuid4(),
        obra_id="OBRA-001",
        codigo="03.02.001",
        descricao="Concretagem",
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=obra)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    calls = 0

    async def fake_execute(_stmt: object) -> MagicMock:
        nonlocal calls
        calls += 1
        return _scalar_result(None if calls == 1 else orc_item)

    session.execute = fake_execute

    with patch("src.services.medicao_service.audit_service.log_event", new_callable=AsyncMock):
        result = await medicao_service.registrar_medicao(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            itens=[
                {
                    "codigo_orcamento": "03.02.001",
                    "quantidade": 5,
                    "valor": 1200,
                }
            ],
        )

    added = [call.args[0] for call in session.add.call_args_list]
    periodo = next(item for item in added if isinstance(item, MedicaoPeriodo))
    medicao = next(item for item in added if isinstance(item, Medicao))
    assert result["status"] == MedicaoPeriodoStatus.ABERTO.value
    assert result["medicoes"] == 1
    assert medicao.periodo_id == periodo.id
    assert medicao.orcamento_item_id == orc_item.id
    assert medicao.quantidade_medida == 5
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_registrar_medicao_rejects_missing_obra() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await medicao_service.registrar_medicao(
            session,
            obra_id="OBRA-INEXISTENTE",
            periodo_ref="2026-06",
            itens=[{"codigo": "03.02.001", "quantidade": 1}],
        )


@pytest.mark.asyncio
async def test_registrar_medicao_rejects_invalid_period() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))

    with pytest.raises(ValidationError, match="YYYY-MM"):
        await medicao_service.registrar_medicao(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-13-01",
            itens=[{"codigo": "03.02.001", "quantidade": 1}],
        )


@pytest.mark.asyncio
async def test_registrar_medicao_rejects_missing_orcamento_item() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))
    calls = 0

    async def fake_execute(_stmt: object) -> MagicMock:
        nonlocal calls
        calls += 1
        return _scalar_result(None)

    session.execute = fake_execute

    with pytest.raises(ValidationError, match="não existe"):
        await medicao_service.registrar_medicao(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            itens=[{"codigo": "03.02.999", "quantidade": 1}],
        )

    assert calls == 2
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_registrar_medicao_rejects_negative_quantity_before_writing() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))
    session.execute = AsyncMock(return_value=_scalar_result(None))

    with pytest.raises(ValidationError, match="negativa"):
        await medicao_service.registrar_medicao(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            itens=[{"codigo": "03.02.001", "quantidade": -1}],
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_registrar_medicao_rejects_closed_period() -> None:
    periodo = MedicaoPeriodo(
        id=uuid.uuid4(),
        obra_id="OBRA-001",
        periodo_ref="2026-06",
        status=MedicaoPeriodoStatus.FECHADO,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))
    session.execute = AsyncMock(return_value=_scalar_result(periodo))

    with pytest.raises(ValidationError, match="já fechado"):
        await medicao_service.registrar_medicao(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            itens=[{"codigo": "03.02.001", "quantidade": 1}],
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_fechar_periodo_rejects_already_closed() -> None:
    periodo = MedicaoPeriodo(
        id=uuid.uuid4(),
        obra_id="OBRA-001",
        periodo_ref="2026-06",
        status=MedicaoPeriodoStatus.FECHADO,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))
    session.execute = AsyncMock(return_value=_scalar_result(periodo))

    with pytest.raises(ValidationError, match="já fechado"):
        await medicao_service.fechar_periodo(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            aprovador="engenheiro",
        )


@pytest.mark.asyncio
async def test_fechar_periodo_rejects_item_without_budget() -> None:
    periodo = MedicaoPeriodo(
        id=uuid.uuid4(),
        obra_id="OBRA-001",
        periodo_ref="2026-06",
        status=MedicaoPeriodoStatus.ABERTO,
    )
    medicao = Medicao(
        obra_id="OBRA-001",
        periodo_id=periodo.id,
        periodo_ref="2026-06",
        orcamento_item_id=None,
        quantidade_medida=1,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))
    session.execute = AsyncMock(side_effect=[_scalar_result(periodo), _rows_result([medicao])])

    with pytest.raises(ValidationError, match="sem orçamento"):
        await medicao_service.fechar_periodo(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            aprovador="engenheiro",
        )


@pytest.mark.asyncio
async def test_fechar_periodo_rejects_negative_quantity() -> None:
    periodo = MedicaoPeriodo(
        id=uuid.uuid4(),
        obra_id="OBRA-001",
        periodo_ref="2026-06",
        status=MedicaoPeriodoStatus.ABERTO,
    )
    medicao = Medicao(
        obra_id="OBRA-001",
        periodo_id=periodo.id,
        periodo_ref="2026-06",
        orcamento_item_id=uuid.uuid4(),
        quantidade_medida=-1,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))
    session.execute = AsyncMock(side_effect=[_scalar_result(periodo), _rows_result([medicao])])

    with pytest.raises(ValidationError, match="quantidade negativa"):
        await medicao_service.fechar_periodo(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            aprovador="engenheiro",
        )


@pytest.mark.asyncio
async def test_fechar_periodo_success() -> None:
    periodo = MedicaoPeriodo(
        id=uuid.uuid4(),
        obra_id="OBRA-001",
        periodo_ref="2026-06",
        status=MedicaoPeriodoStatus.ABERTO,
        metadata_json={},
    )
    medicao = Medicao(
        obra_id="OBRA-001",
        periodo_id=periodo.id,
        periodo_ref="2026-06",
        orcamento_item_id=uuid.uuid4(),
        quantidade_medida=2,
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=Obra(id="OBRA-001", nome="Teste", slug="obra-teste"))
    session.execute = AsyncMock(side_effect=[_scalar_result(periodo), _rows_result([medicao])])
    session.commit = AsyncMock()

    with patch("src.services.medicao_service.audit_service.log_event", new_callable=AsyncMock):
        result = await medicao_service.fechar_periodo(
            session,
            obra_id="OBRA-001",
            periodo_ref="2026-06",
            aprovador="engenheiro",
            comentario="validado",
        )

    assert result["status"] == MedicaoPeriodoStatus.FECHADO.value
    assert periodo.status == MedicaoPeriodoStatus.FECHADO
    assert periodo.closed_at is not None
    assert periodo.metadata_json is not None
    assert periodo.metadata_json["fechamento"]["comentario"] == "validado"
    session.commit.assert_awaited_once()
