from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.core.constants import DocumentStatus
from src.services import admin_service


def _execute_result(*, all_rows=None, scalar=None, scalars_all=None, scalars_first=None):
    result = MagicMock()
    if all_rows is not None:
        result.all.return_value = all_rows
    if scalar is not None:
        result.scalar_one.return_value = scalar
    scalars = MagicMock()
    scalars.all.return_value = scalars_all if scalars_all is not None else []
    scalars.first.return_value = scalars_first
    result.scalars.return_value = scalars
    return result


def test_aguardando_aprovacao_predicate() -> None:
    assert admin_service.AGUARDANDO_APROVACAO == (
        DocumentStatus.RASCUNHO_GERADO,
        DocumentStatus.EM_REVISAO,
    )


async def test_dashboard_counts_groups_and_counts() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result(all_rows=[("received", 3), ("pending_obra", 2)]),
            _execute_result(scalar=5),
        ]
    )

    counts = await admin_service.dashboard_counts(session)

    assert counts["entradas_por_status"] == {"received": 3, "pending_obra": 2}
    assert counts["aguardando_aprovacao"] == 5
    assert counts["pending_obra"] == 2


async def test_list_entradas_passes_status_filter() -> None:
    entradas = [SimpleNamespace(id=uuid.uuid4())]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(scalars_all=entradas))

    result = await admin_service.list_entradas(session, status="pending_obra", limit=10)

    assert result == entradas
    session.execute.assert_awaited_once()


async def test_get_documento_com_triagem_returns_pair() -> None:
    doc = SimpleNamespace(id=uuid.uuid4())
    triagem = SimpleNamespace(id=uuid.uuid4())
    session = AsyncMock()
    session.get = AsyncMock(return_value=doc)
    session.execute = AsyncMock(return_value=_execute_result(scalars_first=triagem))

    found = await admin_service.get_documento_com_triagem(session, doc.id)

    assert found == (doc, triagem)


async def test_get_documento_com_triagem_none_when_missing() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    found = await admin_service.get_documento_com_triagem(session, uuid.uuid4())

    assert found is None
