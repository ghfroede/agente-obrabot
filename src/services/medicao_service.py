from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Medicao, OrcamentoItem
from src.services import audit_service


async def registrar_medicao(
    session: AsyncSession,
    *,
    obra_id: str,
    periodo_ref: str,
    itens: list[dict[str, Any]],
) -> dict[str, Any]:
    created = 0
    for item in itens:
        codigo = item.get("codigo")
        orcamento_item_id = None
        if codigo:
            result = await session.execute(
                select(OrcamentoItem).where(
                    OrcamentoItem.obra_id == obra_id,
                    OrcamentoItem.codigo == str(codigo),
                )
            )
            orc_row = result.scalar_one_or_none()
            if orc_row:
                orcamento_item_id = orc_row.id

        med = Medicao(
            obra_id=obra_id,
            orcamento_item_id=orcamento_item_id,
            periodo_ref=periodo_ref,
            quantidade_medida=float(item.get("quantidade_medida", 0)),
            valor_medido=item.get("valor_medido"),
            metadata_json=item,
        )
        session.add(med)
        created += 1

    await audit_service.log_event(
        session,
        entidade="medicao",
        entidade_id=periodo_ref,
        acao="registrada",
        obra_id=obra_id,
        detalhes={"itens": created},
    )
    await session.commit()
    return {"obra_id": obra_id, "periodo_ref": periodo_ref, "medicoes": created}
